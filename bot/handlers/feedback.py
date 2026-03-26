from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import complaint_context_keyboard, cancel_keyboard, menu_keyboard_for_role
from bot.services.feedback import create_complaint, create_suggestion
from bot.services.notifications import notify_complaint_created, notify_suggestion_created
from bot.services.profile import get_user_by_telegram_id


ASK_COMPLAINT_CONTEXT, ASK_COMPLAINT_TEXT, ASK_SUGGESTION_TEXT = range(50, 53)


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


async def complaint_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END
    if get_user_by_telegram_id(user.id) is None:
        await update.message.reply_text("Сначала заполните профиль.", reply_markup=cancel_keyboard())
        return ConversationHandler.END
    await update.message.reply_text(
        "Если жалоба связана с боем, введите ID боя. Иначе нажмите 'Без боя'.",
        reply_markup=complaint_context_keyboard(),
    )
    return ASK_COMPLAINT_CONTEXT


async def complaint_context_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else '').strip()
    if text == 'Отмена':
        return await cancel_feedback(update, context)
    if text == 'Без боя':
        context.user_data['feedback'] = {'match_id': None}
    else:
        try:
            context.user_data['feedback'] = {'match_id': int(text)}
        except ValueError:
            await update.message.reply_text("ID боя должен быть числом или выберите 'Без боя'.", reply_markup=complaint_context_keyboard())
            return ASK_COMPLAINT_CONTEXT
    await update.message.reply_text("Опишите жалобу одним сообщением.", reply_markup=cancel_keyboard())
    return ASK_COMPLAINT_TEXT


async def complaint_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = (update.message.text if update.message else '').strip()
    if not text or text == 'Отмена':
        return await cancel_feedback(update, context)
    payload = context.user_data.get('feedback', {})
    complaint = create_complaint(from_telegram_id=user.id, text=text, match_id=payload.get('match_id'))
    context.user_data.pop('feedback', None)
    if complaint is None:
        await update.message.reply_text("Не удалось сохранить жалобу.", reply_markup=_menu_keyboard(update))
        return ConversationHandler.END
    await update.message.reply_text("Жалоба отправлена админу.", reply_markup=_menu_keyboard(update))
    await notify_complaint_created(context, user.id, complaint)
    return ConversationHandler.END


async def suggestion_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.message:
        return ConversationHandler.END
    if get_user_by_telegram_id(user.id) is None:
        await update.message.reply_text("Сначала заполните профиль.", reply_markup=cancel_keyboard())
        return ConversationHandler.END
    await update.message.reply_text("Напишите предложение одним сообщением.", reply_markup=cancel_keyboard())
    return ASK_SUGGESTION_TEXT


async def suggestion_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = (update.message.text if update.message else '').strip()
    if not text or text == 'Отмена':
        return await cancel_feedback(update, context)
    suggestion = create_suggestion(from_telegram_id=user.id, text=text)
    if suggestion is None:
        await update.message.reply_text("Не удалось сохранить предложение.", reply_markup=_menu_keyboard(update))
        return ConversationHandler.END
    await update.message.reply_text("Предложение отправлено разработчикам.", reply_markup=_menu_keyboard(update))
    await notify_suggestion_created(context, user.id, suggestion)
    return ConversationHandler.END


async def cancel_feedback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop('feedback', None)
    await update.message.reply_text("Действие отменено.", reply_markup=_menu_keyboard(update))
    return ConversationHandler.END
