from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.keyboards.main import cancel_keyboard, mail_actions_inline, mail_keyboard, search_mode_keyboard
from bot.services.mail import (
    create_mail_message,
    delete_incoming_mail,
    list_incoming_mail,
    search_mail_recipients_by_filters,
    search_mail_recipients_by_full_name,
)
from bot.services.notifications import notify_mail_received
from bot.services.profile import get_user_by_telegram_id


ASK_MAIL_MODE, ASK_MAIL_CLUB, ASK_MAIL_QUERY, ASK_MAIL_RECIPIENT, ASK_MAIL_TEXT = range(70, 75)

MAIL_MODES = {
    "По городу": "city",
    "По моему клубу": "own_club",
    "По конкретному клубу": "club",
    "По ФИО": "full_name",
}


async def mail_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Почта", reply_markup=mail_keyboard())
    return ConversationHandler.END


async def send_pigeon_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    if get_user_by_telegram_id(user.id) is None:
        await update.effective_message.reply_text("Сначала заполните профиль.", reply_markup=cancel_keyboard())
        return ConversationHandler.END
    context.user_data["mail"] = {}
    await update.effective_message.reply_text("Выберите, как искать адресата.", reply_markup=search_mode_keyboard())
    return ASK_MAIL_MODE


async def mail_choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_mail(update, context)
    mode = MAIL_MODES.get(text)
    if mode is None:
        await update.effective_message.reply_text("Выберите режим кнопкой.", reply_markup=search_mode_keyboard())
        return ASK_MAIL_MODE
    context.user_data["mail"]["mode"] = mode
    if mode in {"city", "own_club"}:
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
    context.user_data["mail"]["query"] = text
    return await run_mail_search(update, context)


async def run_mail_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    payload = context.user_data.get("mail", {})
    mode = payload["mode"]
    if mode == "city":
        results = search_mail_recipients_by_filters(requester_telegram_id=user.id)
    elif mode == "own_club":
        results = search_mail_recipients_by_filters(requester_telegram_id=user.id, own_club_only=True)
    elif mode == "club":
        results = search_mail_recipients_by_filters(requester_telegram_id=user.id, club_name=payload.get("club_name"))
    else:
        results = search_mail_recipients_by_full_name(full_name_query=payload.get("query", ""))

    if not results:
        await update.effective_message.reply_text("Никого не нашли.", reply_markup=mail_keyboard())
        context.user_data.pop("mail", None)
        return ConversationHandler.END

    context.user_data["mail"]["recipients"] = [item.telegram_id for item in results[:10]]
    lines = ["Найденные адресаты"]
    for index, item in enumerate(results[:10], start=1):
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
    await update.effective_message.reply_text("Введите текст голубя одним сообщением.", reply_markup=cancel_keyboard())
    return ASK_MAIL_TEXT


async def mail_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = (update.effective_message.text if update.effective_message else "").strip()
    if not text or text == "Отмена":
        return await cancel_mail(update, context)
    recipient_telegram_id = context.user_data.get("mail", {}).get("recipient_telegram_id")
    message, sender, recipient = create_mail_message(
        from_telegram_id=user.id,
        to_telegram_id=recipient_telegram_id,
        text=text,
    )
    context.user_data.pop("mail", None)
    if message is None:
        await update.effective_message.reply_text("Не удалось отправить голубя.", reply_markup=mail_keyboard())
        return ConversationHandler.END
    await update.effective_message.reply_text("Голубь отправлен.", reply_markup=mail_keyboard())
    await notify_mail_received(context, sender, recipient, message)
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
    for item in items[:10]:
        await update.effective_message.reply_text(
            f"<b>От:</b> {escape(item.sender_name)}\n"
            f"<b>ID:</b> {item.message_id}\n"
            f"<b>Получено:</b> {item.created_at:%Y-%m-%d %H:%M}\n\n"
            f"{escape(item.text)}",
            reply_markup=mail_actions_inline(item.message_id),
        )
    return ConversationHandler.END


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
    await update.effective_message.reply_text("Действие отменено.", reply_markup=mail_keyboard())
    return ConversationHandler.END
