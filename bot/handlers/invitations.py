from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot import texts
from bot.config import get_settings
from bot.keyboards.main import (
    WEAPON_LABELS,
    WEAPON_TITLES,
    cancel_keyboard,
    invitation_actions_inline,
    invitations_keyboard,
    menu_keyboard_for_role,
    outgoing_invitation_actions_inline,
    weapons_keyboard,
)
from bot.services.invitations import (
    cancel_invitation,
    create_invitation,
    get_pending_invitation_for_user,
    list_invitations,
    respond_to_invitation,
)
from bot.services.notifications import (
    notify_external_invitation_created,
    notify_invitation_created,
    notify_invitation_cancelled,
    notify_invitation_response,
    notify_match_created,
)
from bot.services.profile import get_user_by_telegram_id


ASK_INVITE_WEAPON, ASK_INVITE_TARGET, ASK_INVITE_ACCEPT_ID, ASK_INVITE_DECLINE_ID = range(30, 34)

INVITATION_STATUS_LABELS = {
    "pending": "🟡 Ожидает ответа",
    "accepted": "🟢 Принята",
    "declined": "🔴 Возвращена",
    "expired": "⚫ Истекла",
    "cancelled": "⚪ Забрана",
}


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


def _format_list(items, title: str) -> str:
    if not items:
        return f"{title}\n\n{texts.INVITE_EMPTY_LIST}"
    lines = [title]
    for item in items[:10]:
        contact = item.external_text or texts.INVITE_EXTERNAL_USER if not item.other_telegram_id else "Зарегистрированный пользователь"
        lines.append(
            f"\n{texts.INVITE_LIST_OPPONENT}: <b>{escape(item.other_name)}</b>\n"
            f"{texts.INVITE_LIST_CONTACT}: <b>{escape(contact)}</b>\n"
            f"{texts.INVITE_LIST_WEAPON}: <b>{escape(WEAPON_TITLES.get(item.weapon_type, item.weapon_type))}</b>\n"
            f"{texts.INVITE_LIST_STATUS}: <b>{escape(INVITATION_STATUS_LABELS.get(item.status, item.status))}</b>\n"
            f"{texts.INVITE_LIST_EXPIRES}: <b>{item.expires_at:%Y-%m-%d}</b>"
        )
    return "\n".join(lines)


async def _send_incoming_with_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    items = list_invitations(telegram_id=user_id, incoming=True)
    await update.effective_message.reply_text(
        _format_list(items, texts.INVITE_INCOMING_TITLE),
        reply_markup=invitations_keyboard(),
    )
    pending = [item for item in items if item.status == "pending"]
    for item in pending[:10]:
        await update.effective_message.reply_text(
            texts.INVITE_ACTION_CARD.format(
                name=f"<b>{escape(item.other_name)}</b>",
                weapon=f"<b>{escape(WEAPON_TITLES.get(item.weapon_type, item.weapon_type))}</b>",
            ),
            reply_markup=invitation_actions_inline(item.invitation_id),
        )


async def _send_outgoing_with_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    items = [item for item in list_invitations(telegram_id=user_id, incoming=False) if item.status == "pending"]
    await update.effective_message.reply_text(
        _format_list(items, texts.INVITE_OUTGOING_TITLE),
        reply_markup=invitations_keyboard(),
    )
    pending = [item for item in items if item.status == "pending"]
    for item in pending[:10]:
        await update.effective_message.reply_text(
            texts.INVITE_OUTGOING_ACTION_CARD.format(
                name=f"<b>{escape(item.other_name)}</b>",
                weapon=f"<b>{escape(WEAPON_TITLES.get(item.weapon_type, item.weapon_type))}</b>",
            ),
            reply_markup=outgoing_invitation_actions_inline(item.invitation_id),
        )


async def invitations_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    profile = get_user_by_telegram_id(user.id)
    if profile is None:
        await update.effective_message.reply_text(texts.INVITE_PROFILE_REQUIRED, reply_markup=cancel_keyboard())
        return ConversationHandler.END

    await _send_incoming_with_actions(update, context, user.id)
    await _send_outgoing_with_actions(update, context, user.id)
    return ConversationHandler.END


async def new_invitation_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.effective_message:
        await update.effective_message.reply_text(texts.INVITE_SELECT_WEAPON, reply_markup=weapons_keyboard(include_done=False))
    context.user_data["invite"] = {}
    return ASK_INVITE_WEAPON


async def invitation_choose_weapon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_invitations(update, context)
    weapon_type = WEAPON_LABELS.get(text)
    if weapon_type is None:
        await update.effective_message.reply_text(texts.INVITE_INVALID_WEAPON, reply_markup=weapons_keyboard(include_done=False))
        return ASK_INVITE_WEAPON
    context.user_data["invite"]["weapon_type"] = weapon_type
    await update.effective_message.reply_text(texts.INVITE_ENTER_TARGET, reply_markup=cancel_keyboard())
    return ASK_INVITE_TARGET


async def invitation_target_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    text = (update.effective_message.text if update.effective_message else "").strip()
    if not text or text == "Отмена":
        return await cancel_invitations(update, context)

    weapon_type = context.user_data["invite"]["weapon_type"]
    result = create_invitation(inviter_telegram_id=tg_user.id, weapon_type=weapon_type, target_text=text)
    inviter = get_user_by_telegram_id(tg_user.id)

    if result.status == "self_invite":
        await update.effective_message.reply_text(texts.INVITE_SELF, reply_markup=invitations_keyboard())
        context.user_data.pop("invite", None)
        return ConversationHandler.END
    if result.status == "inviter_missing":
        await update.effective_message.reply_text(texts.INVITE_PROFILE_REQUIRED, reply_markup=_menu_keyboard(update))
        context.user_data.pop("invite", None)
        return ConversationHandler.END
    if result.status == "ambiguous":
        variants = [f"- {user.full_name}" for user in result.matches[:10]]
        await update.effective_message.reply_text(
            texts.INVITE_AMBIGUOUS_HEADER + "\n\n" + "\n".join(variants),
            reply_markup=invitations_keyboard(),
        )
        context.user_data.pop("invite", None)
        return ConversationHandler.END
    if result.status == "created":
        await update.effective_message.reply_text(
            f"{texts.INVITE_CREATED_PREFIX} {result.invitee.full_name}.",
            reply_markup=invitations_keyboard(),
        )
        await notify_invitation_created(context, inviter, result.invitee, result.invitation)
        context.user_data.pop("invite", None)
        return ConversationHandler.END

    await update.effective_message.reply_text(texts.INVITE_EXTERNAL_CREATED, reply_markup=invitations_keyboard())
    await notify_external_invitation_created(context, inviter, result.invitation, context.bot.username)
    context.user_data.pop("invite", None)
    return ConversationHandler.END


async def incoming_invitations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await _send_incoming_with_actions(update, context, user.id)
    return ConversationHandler.END


async def outgoing_invitations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    await _send_outgoing_with_actions(update, context, user.id)
    return ConversationHandler.END


async def accept_invitation_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(texts.INVITE_ACCEPT_PROMPT, reply_markup=cancel_keyboard())
    return ASK_INVITE_ACCEPT_ID


async def decline_invitation_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(texts.INVITE_DECLINE_PROMPT, reply_markup=cancel_keyboard())
    return ASK_INVITE_DECLINE_ID


async def accept_invitation_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _process_invitation_response(update, context, accept=True)


async def decline_invitation_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _process_invitation_response(update, context, accept=False)


async def invitation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) != 3:
        return
    _, action, raw_id = parts
    try:
        invitation_id = int(raw_id)
    except ValueError:
        return
    if action == "cancel":
        result = cancel_invitation(inviter_telegram_id=update.effective_user.id, invitation_id=invitation_id)
        if result.status == "forbidden":
            await query.edit_message_text(texts.INVITE_CANCEL_FORBIDDEN)
            return
        if result.status == "already_processed":
            await query.edit_message_text(texts.INVITE_ALREADY_PROCESSED)
            return
        if result.status == "expired":
            await query.edit_message_text(texts.INVITE_EXPIRED)
            return
        if result.status != "cancelled":
            await query.edit_message_text(texts.INVITE_MISSING)
            return
        await query.edit_message_text(texts.INVITE_CANCELLED_BY_BUTTON)
        await notify_invitation_cancelled(context, result.inviter, result.invitee, result.invitation)
        return
    accept = action == "accept"
    check = get_pending_invitation_for_user(invitation_id=invitation_id, user_telegram_id=update.effective_user.id)
    if check.status == "forbidden":
        await query.edit_message_text(texts.INVITE_FORBIDDEN)
        return
    if check.status == "already_processed":
        await query.edit_message_text(texts.INVITE_ALREADY_PROCESSED)
        return
    if check.status == "expired":
        await query.edit_message_text(texts.INVITE_EXPIRED)
        return
    if check.status != "ok":
        await query.edit_message_text(texts.INVITE_MISSING)
        return

    result = respond_to_invitation(
        invitee_telegram_id=update.effective_user.id,
        invitation_id=invitation_id,
        accept=accept,
    )
    await query.edit_message_text(texts.INVITE_RESPONSE_ACCEPTED if accept else texts.INVITE_RESPONSE_DECLINED)
    await notify_invitation_response(context, result.inviter, result.invitee, result.invitation, accepted=accept)
    if accept and result.match is not None:
        await notify_match_created(context, result.inviter, result.invitee, result.match)


async def _process_invitation_response(update: Update, context: ContextTypes.DEFAULT_TYPE, accept: bool) -> int:
    user = update.effective_user
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_invitations(update, context)
    try:
        invitation_id = int(text)
    except ValueError:
        await update.effective_message.reply_text(texts.INVITE_INVALID_ID, reply_markup=cancel_keyboard())
        return ASK_INVITE_ACCEPT_ID if accept else ASK_INVITE_DECLINE_ID

    result = respond_to_invitation(invitee_telegram_id=user.id, invitation_id=invitation_id, accept=accept)
    if result.status == "missing":
        await update.effective_message.reply_text(texts.INVITE_MISSING, reply_markup=invitations_keyboard())
        return ConversationHandler.END
    if result.status == "forbidden":
        await update.effective_message.reply_text(texts.INVITE_FORBIDDEN, reply_markup=invitations_keyboard())
        return ConversationHandler.END
    if result.status == "already_processed":
        await update.effective_message.reply_text(texts.INVITE_ALREADY_PROCESSED, reply_markup=invitations_keyboard())
        return ConversationHandler.END
    if result.status == "expired":
        await update.effective_message.reply_text(texts.INVITE_EXPIRED, reply_markup=invitations_keyboard())
        return ConversationHandler.END

    await update.effective_message.reply_text(
        texts.INVITE_RESPONSE_SAVED if accept else texts.INVITE_DECLINED_TEXT,
        reply_markup=invitations_keyboard(),
    )
    await notify_invitation_response(context, result.inviter, result.invitee, result.invitation, accepted=accept)
    if accept and result.match is not None:
        await notify_match_created(context, result.inviter, result.invitee, result.match)
    return ConversationHandler.END


async def cancel_invitations(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("invite", None)
    await update.effective_message.reply_text(texts.INVITE_CANCELLED, reply_markup=invitations_keyboard())
    return ConversationHandler.END
