from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import (
    admin_disputed_match_actions_inline,
    admin_feedback_actions_inline,
    admin_menu_keyboard,
    admin_resolve_inline,
    admin_resolve_keyboard,
    admin_user_actions_inline,
    cancel_keyboard,
    search_mode_keyboard,
)
from bot.services.admin import delete_user_data, get_event_summary, list_matches, list_users, list_users_by_filters
from bot.services.feedback import delete_feedback_item, list_feedback_items
from bot.services.matches import admin_resolve_match
from bot.services.notifications import notify_match_result_confirmed
from bot.services.profile import (
    get_user_by_telegram_id,
    list_known_city_names,
    list_known_club_names,
    normalize_city_name,
    normalize_club_name,
)


ASK_ADMIN_MATCH_ID, ASK_ADMIN_RESOLUTION, ASK_ADMIN_USER_MODE, ASK_ADMIN_USER_CLUB, ASK_ADMIN_USER_QUERY = range(60, 65)
MAX_MESSAGE_LENGTH = 3500

USER_FILTER_MODES = {
    "По городу": "city",
    "По моему клубу": "own_club",
    "По конкретному клубу": "club",
    "По ФИО": "full_name",
}


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    settings = get_settings()
    return bool(user and user.id == settings.admin_telegram_id)


def _numbered_cities_prompt() -> str:
    cities = list_known_city_names()
    lines = ["Выберите город.", ""]
    lines.extend(f"{index}. {city}" for index, city in enumerate(cities, start=1))
    lines.append("")
    lines.append("Введите номер из списка или свой вариант.")
    return "\n".join(lines)


def _numbered_clubs_prompt() -> str:
    clubs = list_known_club_names()
    lines = ["Выберите клуб.", ""]
    lines.extend(f"{index}. {club}" for index, club in enumerate(clubs, start=1))
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


def _resolve_club_input(text: str) -> str:
    clubs = list_known_club_names()
    try:
        index = int(text)
    except ValueError:
        return normalize_club_name(text) or text.strip()
    if 1 <= index <= len(clubs):
        return clubs[index - 1]
    return normalize_club_name(text) or text.strip()


def _deny(update: Update):
    return update.message.reply_text("Этот раздел доступен только администратору.")


async def _reply_chunks(update: Update, header: str, blocks: list[str]) -> None:
    if not blocks:
        await update.message.reply_text(header, reply_markup=admin_menu_keyboard())
        return

    current = header
    sent_first = False
    for block in blocks:
        candidate = f"{current}\n\n{block}" if current else block
        if len(candidate) > MAX_MESSAGE_LENGTH and current:
            await update.message.reply_text(current, reply_markup=admin_menu_keyboard() if not sent_first else None)
            sent_first = True
            current = f"{header}\n\n{block}"
        else:
            current = candidate

    await update.message.reply_text(current, reply_markup=admin_menu_keyboard() if not sent_first else None)


async def _render_admin_users(update: Update, items) -> None:
    if not items:
        await update.message.reply_text("Пользователей не нашли.", reply_markup=admin_menu_keyboard())
        return
    await update.message.reply_text(f"Пользователи: {len(items)}", reply_markup=admin_menu_keyboard())
    for item in items:
        await update.message.reply_text(
            f"{item.name} - {item.club} - {item.city}\nID: {item.telegram_id}",
            reply_markup=admin_user_actions_inline(item.telegram_id),
        )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    await update.message.reply_text("Админ-раздел MVP.", reply_markup=admin_menu_keyboard())


async def admin_ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from bot.services.notifications import notify_admin_ping

    user = update.effective_user
    if not user:
        return

    delivered = await notify_admin_ping(context, user.id)
    if delivered:
        await update.message.reply_text("Тестовое уведомление отправлено админу.")
    else:
        await update.message.reply_text("Не удалось отправить уведомление админу.")


async def admin_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_feedback_items()
    if not items:
        await update.message.reply_text("Обращений пока нет.", reply_markup=admin_menu_keyboard())
        return
    for item in items:
        kind_title = "Жалоба" if item.kind == "complaint" else "Предложение"
        extra = f"\nMatch ID: {item.match_id or '—'}\nСтатус: {item.status}" if item.kind == "complaint" else ""
        await update.message.reply_text(
            (
                f"{kind_title}\n\n"
                f"ID: {item.item_id}\n"
                f"От: {item.from_name} ({item.from_telegram_id}){extra}\n"
                f"Текст: {item.text}"
            ),
            reply_markup=admin_feedback_actions_inline(item.kind, item.item_id),
        )


async def admin_disputed_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_matches(disputed_only=True)
    if not items:
        await update.message.reply_text("Спорных боёв пока нет.", reply_markup=admin_menu_keyboard())
        return
    await update.message.reply_text("Спорные бои", reply_markup=admin_menu_keyboard())
    for item in items:
        await update.message.reply_text(
            (
                f"ID: <b>{item.match_id}</b>\n"
                f"Статус: <b>{escape(item.status)}</b>\n"
                f"Оружие: <b>{escape(item.weapon_type)}</b>\n"
                f"Участники: <b>{escape(item.fighter_a)}</b> vs <b>{escape(item.fighter_b)}</b>"
            ),
            reply_markup=admin_disputed_match_actions_inline(item.match_id),
        )


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update):
        await _deny(update)
        return ConversationHandler.END
    context.user_data["admin_users"] = {}
    await update.message.reply_text("Выберите, как фильтровать пользователей.", reply_markup=search_mode_keyboard())
    return ASK_ADMIN_USER_MODE


async def admin_users_choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await admin_cancel(update, context)

    mode = USER_FILTER_MODES.get(text)
    if mode is None:
        await update.message.reply_text("Выберите режим кнопкой.", reply_markup=search_mode_keyboard())
        return ASK_ADMIN_USER_MODE

    context.user_data["admin_users"]["mode"] = mode
    if mode == "city":
        await update.message.reply_text(_numbered_cities_prompt(), reply_markup=cancel_keyboard())
        return ASK_ADMIN_USER_QUERY
    if mode == "own_club":
        return await admin_users_run_search(update, context)
    if mode == "club":
        await update.message.reply_text(_numbered_clubs_prompt(), reply_markup=cancel_keyboard())
        return ASK_ADMIN_USER_CLUB
    await update.message.reply_text("Введите ФИО полностью или частично.", reply_markup=cancel_keyboard())
    return ASK_ADMIN_USER_QUERY


async def admin_users_club_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await admin_cancel(update, context)
    context.user_data["admin_users"]["club_name"] = _resolve_club_input(text)
    return await admin_users_run_search(update, context)


async def admin_users_query_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await admin_cancel(update, context)
    payload = context.user_data["admin_users"]
    if payload.get("mode") == "city":
        payload["city_name"] = _resolve_city_input(text)
    else:
        payload["query"] = text
    return await admin_users_run_search(update, context)


async def admin_users_run_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    payload = context.user_data.get("admin_users", {})
    mode = payload["mode"]
    profile = get_user_by_telegram_id(user.id)
    settings = get_settings()

    if profile is None and user.id == settings.admin_telegram_id and mode == "own_club":
        await update.message.reply_text(
            "Для этого режима админу нужен профиль. Используйте поиск по городу, клубу или ФИО.",
            reply_markup=search_mode_keyboard(),
        )
        return ASK_ADMIN_USER_MODE

    if mode == "city":
        items = list_users_by_filters(
            requester_telegram_id=user.id,
            city_name=payload.get("city_name"),
        )
    elif mode == "own_club":
        items = list_users_by_filters(requester_telegram_id=user.id, own_club_only=True)
    elif mode == "club":
        items = list_users_by_filters(
            requester_telegram_id=user.id,
            club_name=payload.get("club_name"),
        )
    else:
        items = list_users_by_filters(
            requester_telegram_id=user.id,
            full_name_query=payload.get("query", ""),
        )

    if not items:
        if mode == "full_name":
            await update.message.reply_text("Пользователей не нашли. Введите ФИО еще раз.", reply_markup=cancel_keyboard())
            return ASK_ADMIN_USER_QUERY
        if mode == "city":
            await update.message.reply_text(
                "Пользователей не нашли. Введите номер города или свой вариант еще раз.",
                reply_markup=cancel_keyboard(),
            )
            return ASK_ADMIN_USER_QUERY
        if mode == "club":
            await update.message.reply_text("Пользователей не нашли. Введите название клуба еще раз.", reply_markup=cancel_keyboard())
            return ASK_ADMIN_USER_CLUB
        await update.message.reply_text("Пользователей не нашли.", reply_markup=admin_menu_keyboard())
        context.user_data.pop("admin_users", None)
        return ConversationHandler.END

    context.user_data.pop("admin_users", None)
    await _render_admin_users(update, items)
    return ConversationHandler.END


async def admin_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_matches()
    blocks = []
    for item in items:
        blocks.append(
            f"ID: {item.match_id}\n"
            f"Статус: {item.status}\n"
            f"Оружие: {item.weapon_type}\n"
            f"Участники: {item.fighter_a} vs {item.fighter_b}"
        )
    await _reply_chunks(update, "Матчи", blocks)


async def admin_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    summary = get_event_summary()
    text = (
        "События\n\n"
        f"Пользователей: {summary.users}\n"
        f"Обращений: {summary.complaints_new + summary.suggestions}\n"
        f"Спорных боёв: {summary.disputed_matches}\n"
        f"Ожидающих приглашений: {summary.pending_invitations}"
    )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_resolve_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not _is_admin(update):
        await _deny(update)
        return ConversationHandler.END
    await update.message.reply_text("Введите ID спорного боя.", reply_markup=cancel_keyboard())
    return ASK_ADMIN_MATCH_ID


async def admin_resolve_match_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await admin_cancel(update, context)
    try:
        context.user_data["admin_resolve"] = {"match_id": int(text)}
    except ValueError:
        await update.message.reply_text("ID боя должен быть числом.", reply_markup=cancel_keyboard())
        return ASK_ADMIN_MATCH_ID
    await update.message.reply_text("Выберите итоговое решение.", reply_markup=admin_resolve_keyboard())
    return ASK_ADMIN_RESOLUTION


async def admin_resolve_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await admin_cancel(update, context)
    mapping = {"Победа A": "a", "Победа B": "b", "Ничья": "draw"}
    outcome = mapping.get(text)
    if outcome is None:
        await update.message.reply_text("Выберите вариант кнопкой.", reply_markup=admin_resolve_keyboard())
        return ASK_ADMIN_RESOLUTION
    match_id = context.user_data.get("admin_resolve", {}).get("match_id")
    result = admin_resolve_match(match_id=match_id, outcome=outcome)
    context.user_data.pop("admin_resolve", None)
    if result.status == "missing":
        await update.message.reply_text("Бой не найден.", reply_markup=admin_menu_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("Спорный бой завершен решением администратора.", reply_markup=admin_menu_keyboard())
    await notify_match_result_confirmed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("admin_resolve", None)
    context.user_data.pop("admin_users", None)
    await update.message.reply_text("Действие отменено.", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()

    if update.effective_user.id != get_settings().admin_telegram_id:
        await query.edit_message_text("Это действие доступно только администратору.")
        return

    parts = query.data.split(":")
    if len(parts) < 3 or parts[0] != "admin":
        return

    if parts[1] == "resolve_pick" and len(parts) == 3:
        try:
            match_id = int(parts[2])
        except ValueError:
            return
        await query.edit_message_reply_markup(reply_markup=admin_resolve_inline(match_id))
        return

    if parts[1] == "feedback_delete" and len(parts) == 4:
        kind = parts[2]
        try:
            item_id = int(parts[3])
        except ValueError:
            return
        if not delete_feedback_item(kind=kind, item_id=item_id):
            await query.edit_message_text("Не удалось удалить обращение.")
            return
        await query.edit_message_text("Обращение удалено.")
        return

    if parts[1] == "user_delete" and len(parts) == 3:
        try:
            telegram_id = int(parts[2])
        except ValueError:
            return
        if not delete_user_data(telegram_id):
            await query.edit_message_text("Не удалось удалить пользователя.")
            return
        await query.edit_message_text("Пользователь удален.")
        return

    if len(parts) != 4 or parts[1] != "resolve":
        return

    outcome = parts[2]
    try:
        match_id = int(parts[3])
    except ValueError:
        return

    if outcome not in {"a", "b", "draw"}:
        return

    result = admin_resolve_match(match_id=match_id, outcome=outcome)
    if result.status == "missing":
        await query.edit_message_text("Бой не найден.")
        return

    await query.edit_message_text("Спорный бой завершен решением администратора.")
    await notify_match_result_confirmed(
        context,
        result.actor,
        result.other,
        result.match,
        result.winner,
        result.match.proposed_is_draw,
    )
