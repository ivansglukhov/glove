from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import admin_menu_keyboard, admin_resolve_keyboard, cancel_keyboard
from bot.services.admin import get_event_summary, list_matches, list_users
from bot.services.feedback import list_complaints, list_suggestions
from bot.services.matches import admin_resolve_match
from bot.services.notifications import notify_match_result_confirmed


ASK_ADMIN_MATCH_ID, ASK_ADMIN_RESOLUTION = range(60, 62)


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    settings = get_settings()
    return bool(user and user.id == settings.admin_telegram_id)


def _deny(update: Update):
    return update.message.reply_text("Этот раздел доступен только администратору.")


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


async def admin_complaints(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_complaints()[:10]
    if not items:
        await update.message.reply_text("Жалоб пока нет.", reply_markup=admin_menu_keyboard())
        return
    text = "Жалобы"
    for item in items:
        text += (
            f"\n\nID: {item.complaint_id}\n"
            f"От: {item.from_name} ({item.from_telegram_id})\n"
            f"Match ID: {item.match_id or '—'}\n"
            f"Статус: {item.status}\n"
            f"Текст: {item.text}"
        )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_suggestions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_suggestions()[:10]
    if not items:
        await update.message.reply_text("Предложений пока нет.", reply_markup=admin_menu_keyboard())
        return
    text = "Предложения"
    for item in items:
        text += (
            f"\n\nID: {item.suggestion_id}\n"
            f"От: {item.from_name} ({item.from_telegram_id})\n"
            f"Текст: {item.text}"
        )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_disputed_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_matches(disputed_only=True)
    if not items:
        await update.message.reply_text("Спорных боёв пока нет.", reply_markup=admin_menu_keyboard())
        return
    text = "Спорные бои"
    for item in items:
        text += (
            f"\n\nID: {item.match_id}\n"
            f"Статус: {item.status}\n"
            f"Оружие: {item.weapon_type}\n"
            f"Участники: {item.fighter_a} vs {item.fighter_b}"
        )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_users()
    text = "Пользователи"
    for item in items:
        text += (
            f"\n\n{item.name}\n"
            f"Telegram ID: {item.telegram_id}\n"
            f"Город: {item.city}\n"
            f"Клуб: {item.club}\n"
            f"Регистрация: {item.registered_at:%Y-%m-%d}"
        )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    items = list_matches()
    text = "Матчи"
    for item in items:
        text += (
            f"\n\nID: {item.match_id}\n"
            f"Статус: {item.status}\n"
            f"Оружие: {item.weapon_type}\n"
            f"Участники: {item.fighter_a} vs {item.fighter_b}"
        )
    await update.message.reply_text(text, reply_markup=admin_menu_keyboard())


async def admin_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update):
        await _deny(update)
        return
    summary = get_event_summary()
    text = (
        "События\n\n"
        f"Пользователей: {summary.users}\n"
        f"Новых жалоб: {summary.complaints_new}\n"
        f"Предложений: {summary.suggestions}\n"
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
    text = (update.message.text if update.message else '').strip()
    if text == 'Отмена':
        return await admin_cancel(update, context)
    try:
        context.user_data['admin_resolve'] = {'match_id': int(text)}
    except ValueError:
        await update.message.reply_text("ID боя должен быть числом.", reply_markup=cancel_keyboard())
        return ASK_ADMIN_MATCH_ID
    await update.message.reply_text("Выберите итоговое решение.", reply_markup=admin_resolve_keyboard())
    return ASK_ADMIN_RESOLUTION


async def admin_resolve_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else '').strip()
    if text == 'Отмена':
        return await admin_cancel(update, context)
    mapping = {'Победа A': 'a', 'Победа B': 'b', 'Ничья': 'draw'}
    outcome = mapping.get(text)
    if outcome is None:
        await update.message.reply_text("Выберите вариант кнопкой.", reply_markup=admin_resolve_keyboard())
        return ASK_ADMIN_RESOLUTION
    match_id = context.user_data.get('admin_resolve', {}).get('match_id')
    result = admin_resolve_match(match_id=match_id, outcome=outcome)
    context.user_data.pop('admin_resolve', None)
    if result.status == 'missing':
        await update.message.reply_text("Бой не найден.", reply_markup=admin_menu_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("Спорный бой завершен решением администратора.", reply_markup=admin_menu_keyboard())
    await notify_match_result_confirmed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    return ConversationHandler.END


async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('admin_resolve', None)
    await update.message.reply_text("Действие отменено.", reply_markup=admin_menu_keyboard())
    return ConversationHandler.END
