from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes


logger = logging.getLogger(__name__)


async def log_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    if isinstance(update, Update):
        user_id = update.effective_user.id if update.effective_user else 'unknown'
        chat_id = update.effective_chat.id if update.effective_chat else 'unknown'
        logger.exception('Unhandled bot error. user=%s chat=%s', user_id, chat_id, exc_info=context.error)
        return

    logger.exception('Unhandled bot error without Update context', exc_info=context.error)
