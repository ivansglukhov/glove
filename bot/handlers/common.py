from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.keyboards.main import menu_keyboard_for_role
from bot.services.invitations import claim_external_invitation
from bot.services.notifications import notify_external_invitation_linked
from bot.texts import (
    DEEPLINK_ALREADY_PROCESSED_TEXT,
    DEEPLINK_EXPIRED_TEXT,
    DEEPLINK_FORBIDDEN_TEXT,
    DEEPLINK_LINKED_TEXT,
    DEEPLINK_SELF_TEXT,
    HELP_TEXT,
    SEED_INFO_TEXT,
    START_WELCOME,
)


def _menu_keyboard(update: Update):
    settings = get_settings()
    user = update.effective_user
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message:
        return

    if context.args and context.args[0].startswith("invite_"):
        raw = context.args[0].split("_", 1)[1]
        try:
            invitation_id = int(raw)
        except ValueError:
            invitation_id = None

        if invitation_id is not None:
            result = claim_external_invitation(invitation_id=invitation_id, invitee_telegram_id=user.id)
            if result.status in {"linked", "already_linked"}:
                await update.message.reply_text(DEEPLINK_LINKED_TEXT, reply_markup=_menu_keyboard(update))
                if result.status == "linked":
                    await notify_external_invitation_linked(context, result.inviter, result.invitee, result.invitation)
                return
            if result.status == "self_invite":
                await update.message.reply_text(DEEPLINK_SELF_TEXT, reply_markup=_menu_keyboard(update))
                return
            if result.status == "expired":
                await update.message.reply_text(DEEPLINK_EXPIRED_TEXT, reply_markup=_menu_keyboard(update))
                return
            if result.status == "forbidden":
                await update.message.reply_text(DEEPLINK_FORBIDDEN_TEXT, reply_markup=_menu_keyboard(update))
                return
            if result.status == "already_processed":
                await update.message.reply_text(DEEPLINK_ALREADY_PROCESSED_TEXT, reply_markup=_menu_keyboard(update))
                return

    await update.message.reply_text(START_WELCOME, reply_markup=_menu_keyboard(update))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT)


async def seed_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(SEED_INFO_TEXT)
