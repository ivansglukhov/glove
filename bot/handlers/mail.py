from __future__ import annotations

import logging
from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import cancel_keyboard, mail_actions_inline, mail_keyboard, menu_keyboard_for_role, search_mode_keyboard
from bot.services.mail import (
    create_mail_broadcast,
    create_mail_message,
    delete_incoming_mail,
    list_incoming_mail,
    list_outgoing_mail,
    search_mail_recipients_by_filters,
    search_mail_recipients_by_full_name,
)
from bot.services.notifications import notify_mail_received
from bot.services.profile import get_user_by_telegram_id, list_known_city_names, normalize_city_name


ASK_MAIL_MODE, ASK_MAIL_CLUB, ASK_MAIL_QUERY, ASK_MAIL_RECIPIENT, ASK_MAIL_TEXT = range(70, 75)
logger = logging.getLogger(__name__)

MAIL_MODES = {
    "По городу": "city",
    "По моему клубу": "own_club",
    "По конкретному клубу": "club",
    "По ФИО": "full_name",
}


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


def _numbered_cities_prompt() -> str:
    cities = list_known_city_names()
    lines = ["Выберите город.", ""]
    lines.extend(f"{index}. {city}" for index, city in enumerate(cities, start=1))
    lines.append("")
    lines.append("Введите номер из списка или свой вариант.")
    return "\n".join(lines)


def _resolve_city_input(text: str) -> str:
    cities = list_known_city_names()
    try:
        index = int(text)
    except ValueError:
        return normalize_city_name(text)
    if 1 <= index <= len(cities):
        return normalize_city_name(cities[index - 1])
    return normalize_city_name(text)


async def mail_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Почта", reply_markup=mail_keyboard())
    return ConversationHandler.END


async def send_pigeon_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    profile = get_user_by_telegram_id(user.id)
    settings = get_settings()
    if profile is None and user.id != settings.admin_telegram_id:
        await update.effective_message.reply_text("Сначала заполните профиль.", reply_markup=cancel_keyboard())
        return ConversationHandler.END
    context.user_data["mail"] = {}
    await update.effective_message.reply_text("Выберите, как искать адресата.", reply_markup=search_mode_keyboard())
    return ASK_MAIL_MODE


async def send_all_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    settings = get_settings()
    if not user or not update.effective_message:
        return ConversationHandler.END
    if user.id != settings.admin_telegram_id:
        await update.effective_message.reply_text("Это действие доступно только админу.", reply_markup=_menu_keyboard(update))
        return ConversationHandler.END
    context.user_data["mail"] = {"broadcast_all": True}
    await update.effective_message.reply_text(
        "Введите текст, отправьте одно фото или один стикер для всех пользователей.",
        reply_markup=cancel_keyboard(),
    )
    return ASK_MAIL_TEXT


async def mail_choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_mail(update, context)
    mode = MAIL_MODES.get(text)
    if mode is None:
        await update.effective_message.reply_text("Выберите режим кнопкой.", reply_markup=search_mode_keyboard())
        return ASK_MAIL_MODE
    context.user_data["mail"]["mode"] = mode
    if mode == "city":
        await update.effective_message.reply_text(_numbered_cities_prompt(), reply_markup=cancel_keyboard())
        return ASK_MAIL_QUERY
    if mode == "own_club":
        return await run_mail_search(update, context)
    if mode == "club":
        await update.effective_message.reply_text("Введите точное название клуба.", reply_markup=cancel_keyboard())
        return ASK_MAIL_CLUB
    await update.effective_message.reply_text("Введите ФИО полностью или частично.", reply_markup=cancel_keyboard())
    return ASK_MAIL_QUERY


async def mail_club_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if not text or text == "Отмена":
        return await cancel_mail(update, context)
    context.user_data["mail"]["club_name"] = text
    return await run_mail_search(update, context)


async def mail_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if not text or text == "Отмена":
        return await cancel_mail(update, context)
    payload = context.user_data["mail"]
    if payload.get("mode") == "city":
        payload["city_name"] = _resolve_city_input(text)
    else:
        payload["query"] = text
    return await run_mail_search(update, context)


async def run_mail_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    payload = context.user_data.get("mail", {})
    mode = payload["mode"]
    profile = get_user_by_telegram_id(user.id)
    settings = get_settings()
    if profile is None and user.id == settings.admin_telegram_id and mode in {"city", "own_club"}:
        await update.effective_message.reply_text(
            "Для этого режима админу нужен профиль. Используйте поиск по клубу или ФИО.",
            reply_markup=search_mode_keyboard(),
        )
        return ASK_MAIL_MODE

    if mode == "city":
        results = search_mail_recipients_by_filters(
            requester_telegram_id=user.id,
            city_name=payload.get("city_name"),
        )
    elif mode == "own_club":
        results = search_mail_recipients_by_filters(requester_telegram_id=user.id, own_club_only=True)
    elif mode == "club":
        results = search_mail_recipients_by_filters(requester_telegram_id=user.id, club_name=payload.get("club_name"))
    else:
        results = search_mail_recipients_by_full_name(full_name_query=payload.get("query", ""))

    if not results:
        if mode == "full_name":
            await update.effective_message.reply_text(
                "Никого не нашли. Введите ФИО еще раз.",
                reply_markup=cancel_keyboard(),
            )
            return ASK_MAIL_QUERY
        if mode == "city":
            await update.effective_message.reply_text(
                "Никого не нашли. Введите номер города или свой вариант еще раз.",
                reply_markup=cancel_keyboard(),
            )
            return ASK_MAIL_QUERY
        if mode == "club":
            await update.effective_message.reply_text(
                "Никого не нашли. Введите название клуба еще раз.",
                reply_markup=cancel_keyboard(),
            )
            return ASK_MAIL_CLUB
        await update.effective_message.reply_text("Никого не нашли.", reply_markup=mail_keyboard())
        context.user_data.pop("mail", None)
        return ConversationHandler.END

    context.user_data["mail"]["recipients"] = [item.telegram_id for item in results]
    lines = ["Найденные адресаты"]
    for index, item in enumerate(results, start=1):
        lines.append(
            f"\n<b>{index}. {escape(item.full_name)}</b>\n"
            f"<b>Клуб:</b> {escape(item.club_name)}\n"
            f"<b>Город:</b> {escape(item.city)}"
        )
    lines.append("\nВведите <b>номер адресата</b> из списка.")
    await update.effective_message.reply_text("\n".join(lines), reply_markup=cancel_keyboard())
    return ASK_MAIL_RECIPIENT


async def mail_recipient_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_mail(update, context)
    try:
        index = int(text)
    except ValueError:
        await update.effective_message.reply_text("Введите номер адресата из списка.", reply_markup=cancel_keyboard())
        return ASK_MAIL_RECIPIENT
    recipients = context.user_data.get("mail", {}).get("recipients", [])
    if index < 1 or index > len(recipients):
        await update.effective_message.reply_text("Такого номера нет в списке.", reply_markup=cancel_keyboard())
        return ASK_MAIL_RECIPIENT
    context.user_data["mail"]["recipient_telegram_id"] = recipients[index - 1]
    context.chat_data["mail_recipient_telegram_id"] = recipients[index - 1]
    await update.effective_message.reply_text(
        "Введите текст, отправьте одно фото или один стикер.",
        reply_markup=cancel_keyboard(),
    )
    return ASK_MAIL_TEXT


async def mail_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    message = update.effective_message
    text = (message.text if message and message.text else message.caption if message and message.caption else "").strip()
    photo = message.photo[-1] if message and message.photo else None
    photo_file_id = photo.file_id if photo else None
    sticker = message.sticker if message else None
    sticker_file_id = sticker.file_id if sticker else None

    if text == "Отмена":
        return await cancel_mail(update, context)
    if not text and photo_file_id is None and sticker_file_id is None:
        await update.effective_message.reply_text(
            "Отправьте текст, одно фото с подписью или без нее, или один стикер.",
            reply_markup=cancel_keyboard(),
        )
        return ASK_MAIL_TEXT

    payload = context.user_data.get("mail", {})
    if payload.get("broadcast_all"):
        sender, created = create_mail_broadcast(
            from_telegram_id=user.id,
            text=text,
            photo_file_id=photo_file_id,
            sticker_file_id=sticker_file_id,
        )
        if sender is None:
            await update.effective_message.reply_text("Не удалось отправить сообщение.", reply_markup=mail_keyboard())
            return ConversationHandler.END
        context.user_data.pop("mail", None)
        context.chat_data.pop("mail_recipient_telegram_id", None)
        for created_message, recipient in created:
            await notify_mail_received(context, sender, recipient, created_message)
        await update.effective_message.reply_text(
            f"Сообщение отправлено всем. Получателей: {len(created)}.",
            reply_markup=mail_keyboard(),
        )
        return ConversationHandler.END

    recipient_telegram_id = payload.get("recipient_telegram_id") or context.chat_data.get("mail_recipient_telegram_id")
    logger.warning(
        "mail_text_input sender=%s recipient=%s has_photo=%s has_sticker=%s text_len=%s payload=%s chat_recipient=%s",
        user.id if user else None,
        recipient_telegram_id,
        bool(photo_file_id),
        bool(sticker_file_id),
        len(text),
        payload,
        context.chat_data.get("mail_recipient_telegram_id"),
    )
    if recipient_telegram_id is None:
        await update.effective_message.reply_text(
            "Не удалось определить адресата. Выберите адресата еще раз.",
            reply_markup=mail_keyboard(),
        )
        context.user_data.pop("mail", None)
        context.chat_data.pop("mail_recipient_telegram_id", None)
        return ConversationHandler.END

    created_message, sender, recipient = create_mail_message(
        from_telegram_id=user.id,
        to_telegram_id=recipient_telegram_id,
        text=text,
        photo_file_id=photo_file_id,
        sticker_file_id=sticker_file_id,
    )
    if created_message is None:
        await update.effective_message.reply_text(
            "Не удалось отправить голубя. Попробуйте еще раз текстом, одним фото или одним стикером.",
            reply_markup=cancel_keyboard(),
        )
        return ASK_MAIL_TEXT

    context.user_data.pop("mail", None)
    context.chat_data.pop("mail_recipient_telegram_id", None)
    await update.effective_message.reply_text("Голубь отправлен.", reply_markup=mail_keyboard())
    await notify_mail_received(context, sender, recipient, created_message)
    return ConversationHandler.END


async def incoming_mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    items = list_incoming_mail(recipient_telegram_id=user.id)
    if not items:
        await update.effective_message.reply_text("Почтовый ящик пуст.", reply_markup=mail_keyboard())
        return ConversationHandler.END
    await update.effective_message.reply_text("Входящие", reply_markup=mail_keyboard())
    for item in items:
        body = (
            f"<b>От:</b> {escape(item.sender_name)}\n"
            f"<b>ID:</b> {item.message_id}\n"
            f"<b>Получено:</b> {item.created_at:%Y-%m-%d %H:%M}"
        )
        if item.text:
            body += f"\n\n{escape(item.text)}"
        if item.photo_file_id:
            await update.effective_message.reply_photo(
                photo=item.photo_file_id,
                caption=body,
                reply_markup=mail_actions_inline(item.message_id),
            )
        elif item.sticker_file_id:
            await update.effective_message.reply_text(
                body,
                reply_markup=mail_actions_inline(item.message_id),
            )
            await update.effective_message.reply_sticker(sticker=item.sticker_file_id)
        else:
            await update.effective_message.reply_text(
                body,
                reply_markup=mail_actions_inline(item.message_id),
            )
    return ConversationHandler.END


async def outgoing_mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    items = list_outgoing_mail(sender_telegram_id=user.id)
    if not items:
        await update.effective_message.reply_text("Улетевших голубей пока нет.", reply_markup=mail_keyboard())
        return ConversationHandler.END
    await update.effective_message.reply_text("Улетевшие", reply_markup=mail_keyboard())
    for item in items:
        body = (
            f"<b>Кому:</b> {escape(item.recipient_name)}\n"
            f"<b>ID:</b> {item.message_id}\n"
            f"<b>Отправлено:</b> {item.created_at:%Y-%m-%d %H:%M}"
        )
        if item.text:
            body += f"\n\n{escape(item.text)}"
        if item.photo_file_id:
            await update.effective_message.reply_photo(photo=item.photo_file_id, caption=body)
        elif item.sticker_file_id:
            await update.effective_message.reply_text(body)
            await update.effective_message.reply_sticker(sticker=item.sticker_file_id)
        else:
            await update.effective_message.reply_text(body)
    return ConversationHandler.END


async def mail_reply_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query or not update.effective_user:
        return ConversationHandler.END
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "mail" or parts[1] not in {"reply", "send"}:
        return ConversationHandler.END
    try:
        message_id = int(parts[2])
    except ValueError:
        return ConversationHandler.END

    item = next(
        (mail for mail in list_incoming_mail(recipient_telegram_id=update.effective_user.id) if mail.message_id == message_id),
        None,
    )
    if item is None:
        await query.edit_message_text("Не удалось найти это сообщение.")
        return ConversationHandler.END

    context.user_data["mail"] = {"recipient_telegram_id": item.sender_telegram_id}
    context.chat_data["mail_recipient_telegram_id"] = item.sender_telegram_id
    await query.message.reply_text(
        f"Сообщение для <b>{escape(item.sender_name)}</b>.\n\nВведите текст, отправьте одно фото или один стикер.",
        reply_markup=cancel_keyboard(),
    )
    return ASK_MAIL_TEXT


async def mail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3 or parts[0] != "mail" or parts[1] != "delete":
        return
    try:
        message_id = int(parts[2])
    except ValueError:
        return
    if not delete_incoming_mail(recipient_telegram_id=update.effective_user.id, message_id=message_id):
        await query.edit_message_text("Не удалось удалить сообщение.")
        return
    await query.edit_message_text("Сообщение удалено.")


async def cancel_mail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("mail", None)
    context.chat_data.pop("mail_recipient_telegram_id", None)
    await update.effective_message.reply_text("Действие отменено.", reply_markup=_menu_keyboard(update))
    return ConversationHandler.END
