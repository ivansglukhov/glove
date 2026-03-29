from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot import texts
from bot.config import get_settings
from bot.keyboards.main import (
    READINESS_TITLES,
    WEAPON_LABELS,
    WEAPON_TITLES,
    cancel_keyboard,
    menu_keyboard_for_role,
    search_mode_keyboard,
    search_result_actions_inline,
    weapons_keyboard,
)
from bot.services.invitations import create_invitation
from bot.services.notifications import notify_external_invitation_created, notify_invitation_created
from bot.services.profile import get_user_by_telegram_id
from bot.services.search import search_by_filters, search_by_full_name


ASK_SEARCH_WEAPON, ASK_SEARCH_MODE, ASK_SEARCH_CLUB, ASK_SEARCH_QUERY = range(20, 24)

SEARCH_MODES = {
    "По городу": "city",
    "По моему клубу": "own_club",
    "По конкретному клубу": "club",
    "По ФИО": "full_name",
}


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


def _format_result(item, index: int) -> str:
    card = item.card
    readiness = READINESS_TITLES.get(card.readiness_status, card.readiness_status)
    return (
        f"<b>{index}. {escape(card.full_name)}</b>\n"
        f"<b>ФИО:</b> {escape(card.full_name)}\n"
        f"<b>Клуб:</b> {escape(card.club_name)}\n"
        f"<b>Город:</b> {escape(card.city)}\n"
        f"<b>Оружие:</b> {escape(WEAPON_TITLES.get(card.weapon_type, card.weapon_type))}\n"
        f"<b>Статус:</b> {escape(readiness)}\n"
        f"<b>Винрейт:</b> {card.win_rate}%\n"
        f"<b>Рейтинг:</b> {card.rating}"
    )


async def search_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return ConversationHandler.END

    user = get_user_by_telegram_id(tg_user.id)
    if user is None:
        await update.message.reply_text(texts.SEARCH_PROFILE_REQUIRED, reply_markup=cancel_keyboard())
        return ConversationHandler.END

    context.user_data["search"] = {}
    await update.message.reply_text(texts.SEARCH_SELECT_WEAPON, reply_markup=weapons_keyboard(include_done=False))
    return ASK_SEARCH_WEAPON


async def choose_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_search(update, context)

    weapon_type = WEAPON_LABELS.get(text)
    if weapon_type is None:
        await update.message.reply_text(texts.SEARCH_INVALID_WEAPON, reply_markup=weapons_keyboard(include_done=False))
        return ASK_SEARCH_WEAPON

    context.user_data["search"]["weapon_type"] = weapon_type
    await update.message.reply_text(texts.SEARCH_SELECT_MODE, reply_markup=search_mode_keyboard())
    return ASK_SEARCH_MODE


async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_search(update, context)

    mode = SEARCH_MODES.get(text)
    if mode is None:
        await update.message.reply_text(texts.SEARCH_INVALID_MODE, reply_markup=search_mode_keyboard())
        return ASK_SEARCH_MODE

    context.user_data["search"]["mode"] = mode
    if mode in {"city", "own_club"}:
        return await run_search(update, context)
    if mode == "club":
        await update.message.reply_text(texts.SEARCH_ENTER_CLUB, reply_markup=cancel_keyboard())
        return ASK_SEARCH_CLUB
    await update.message.reply_text(texts.SEARCH_ENTER_FULL_NAME, reply_markup=cancel_keyboard())
    return ASK_SEARCH_QUERY


async def club_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await cancel_search(update, context)
    context.user_data["search"]["club_name"] = text
    return await run_search(update, context)


async def query_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await cancel_search(update, context)
    context.user_data["search"]["query"] = text
    return await run_search(update, context)


async def run_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    payload = context.user_data.get("search", {})
    weapon_type = payload["weapon_type"]
    mode = payload["mode"]

    if mode == "city":
        results = search_by_filters(requester_telegram_id=tg_user.id, weapon_type=weapon_type)
    elif mode == "own_club":
        results = search_by_filters(requester_telegram_id=tg_user.id, weapon_type=weapon_type, own_club_only=True)
    elif mode == "club":
        results = search_by_filters(
            requester_telegram_id=tg_user.id,
            weapon_type=weapon_type,
            club_name=payload.get("club_name"),
        )
    else:
        results = search_by_full_name(full_name_query=payload.get("query", ""), weapon_type=weapon_type)

    if not results:
        await update.message.reply_text(texts.SEARCH_NO_RESULTS, reply_markup=_menu_keyboard(update))
        context.user_data.pop("search", None)
        return ConversationHandler.END

    await update.message.reply_text(
        f"<b>Найдено:</b> {len(results)}",
        reply_markup=_menu_keyboard(update),
        parse_mode="HTML",
    )
    for index, result in enumerate(results, start=1):
        await update.message.reply_text(
            _format_result(result, index),
            parse_mode="HTML",
            reply_markup=search_result_actions_inline(weapon_type, result.card.telegram_id),
        )

    await update.message.reply_text(texts.SEARCH_FALLBACK_INVITE, reply_markup=_menu_keyboard(update))
    context.user_data.pop("search", None)
    return ConversationHandler.END


async def search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 4 or parts[0] != "srch" or parts[1] != "invite":
        return

    weapon_type = parts[2]
    try:
        target_telegram_id = int(parts[3])
    except ValueError:
        await query.edit_message_reply_markup(reply_markup=None)
        return

    result = create_invitation(
        inviter_telegram_id=update.effective_user.id,
        weapon_type=weapon_type,
        target_text=str(target_telegram_id),
    )
    inviter = get_user_by_telegram_id(update.effective_user.id)

    if result.status == "self_invite":
        await query.answer(texts.SEARCH_SELF_INVITE, show_alert=True)
        return
    if result.status == "created":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"{texts.INVITE_CREATED_PREFIX} <b>{escape(result.invitee.full_name)}</b>.",
            parse_mode="HTML",
        )
        await notify_invitation_created(context, inviter, result.invitee, result.invitation)
        return
    if result.status == "external_created":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(texts.SEARCH_EXTERNAL_CREATED)
        await notify_external_invitation_created(context, inviter, result.invitation, context.bot.username)
        return

    await query.answer(texts.SEARCH_CREATE_FAILED, show_alert=True)


async def cancel_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("search", None)
    await update.message.reply_text(texts.SEARCH_CANCELLED, reply_markup=_menu_keyboard(update))
    return ConversationHandler.END
