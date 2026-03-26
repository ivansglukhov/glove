from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import (
    WEAPON_TITLES,
    cancel_keyboard,
    match_actions_inline,
    matches_keyboard,
    menu_keyboard_for_role,
    result_keyboard,
)
from bot.services.matches import confirm_match_result, list_matches, propose_match_result
from bot.services.notifications import notify_match_result_confirmed, notify_match_result_disputed, notify_match_result_proposed
from bot.services.profile import get_user_by_telegram_id


ASK_MATCH_ID, ASK_MATCH_OUTCOME, ASK_MATCH_NOTE, ASK_CONFIRM_ID, ASK_DISPUTE_ID = range(40, 45)

RESULT_LABELS = {
    "Моя победа": "self",
    "Победа соперника": "other",
    "Ничья": "draw",
}


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


def _result_text(item) -> str:
    if item.proposed_is_draw:
        return "<b>ничья</b>"
    if item.proposed_winner_name:
        return f"<b>победа {escape(item.proposed_winner_name)}</b>"
    return "результат не предложен"


async def _send_matches_with_actions(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    items = list_matches(user_id)
    if not items:
        await update.effective_message.reply_text("Список боёв\n\nПока боёв нет.", reply_markup=matches_keyboard())
        return

    lines = ["Список боёв"]
    for item in items[:10]:
        lines.append(
            f"\nID: <b>{item.match_id}</b>\n"
            f"Соперник: <b>{escape(item.other_name)}</b>\n"
            f"Оружие: <b>{escape(WEAPON_TITLES.get(item.weapon_type, item.weapon_type))}</b>\n"
            f"Статус: <b>{escape(item.status)}</b>\n"
            f"Результат: {_result_text(item)}\n"
            f"Моё примечание: <b>{escape(item.my_note or '—')}</b>"
        )
    await update.effective_message.reply_text("\n".join(lines), reply_markup=matches_keyboard())

    for item in items[:10]:
        can_propose = item.status in {"active", "disputed"}
        can_confirm = item.status == "awaiting_confirmation"
        markup = match_actions_inline(item.match_id, can_propose=can_propose, can_confirm=can_confirm)
        if markup is not None:
            await update.effective_message.reply_text(
                f"Бой <b>#{item.match_id}</b>: <b>{escape(item.other_name)}</b> (<b>{escape(WEAPON_TITLES.get(item.weapon_type, item.weapon_type))}</b>)",
                reply_markup=markup,
            )


async def matches_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    profile = get_user_by_telegram_id(user.id)
    if profile is None:
        await update.effective_message.reply_text("Сначала заполните профиль.", reply_markup=cancel_keyboard())
        return ConversationHandler.END
    await _send_matches_with_actions(update, context, user.id)
    return ConversationHandler.END


async def propose_result_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Введите ID боя.", reply_markup=cancel_keyboard())
    return ASK_MATCH_ID


async def propose_result_match_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_matches(update, context)
    try:
        context.user_data["match_flow"] = {"match_id": int(text)}
    except ValueError:
        await update.effective_message.reply_text("ID боя должен быть числом.", reply_markup=cancel_keyboard())
        return ASK_MATCH_ID
    await update.effective_message.reply_text("Выберите результат.", reply_markup=result_keyboard())
    return ASK_MATCH_OUTCOME


async def propose_result_outcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_matches(update, context)
    outcome = RESULT_LABELS.get(text)
    if outcome is None:
        await update.effective_message.reply_text("Выберите результат кнопкой.", reply_markup=result_keyboard())
        return ASK_MATCH_OUTCOME
    context.user_data["match_flow"]["outcome"] = outcome
    await update.effective_message.reply_text(
        "Введите примечание или отправьте '-' если не хотите добавлять. Это примечание увидите только вы.",
        reply_markup=cancel_keyboard(),
    )
    return ASK_MATCH_NOTE


async def propose_result_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_matches(update, context)
    payload = context.user_data.get("match_flow", {})
    note_text = None if text == "-" else text
    result = propose_match_result(
        actor_telegram_id=user.id,
        match_id=payload["match_id"],
        outcome=payload["outcome"],
        note_text=note_text,
    )
    context.user_data.pop("match_flow", None)
    if result.status == "missing":
        await update.effective_message.reply_text("Бой не найден.", reply_markup=matches_keyboard())
        return ConversationHandler.END
    if result.status == "forbidden":
        await update.effective_message.reply_text("Этот бой вам не принадлежит.", reply_markup=matches_keyboard())
        return ConversationHandler.END
    if result.status == "already_completed":
        await update.effective_message.reply_text("Этот бой уже завершён.", reply_markup=matches_keyboard())
        return ConversationHandler.END

    await update.effective_message.reply_text("Результат предложен.", reply_markup=matches_keyboard())
    await notify_match_result_proposed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    return ConversationHandler.END


async def match_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    parts = query.data.split(":")
    if len(parts) < 3 or parts[0] != "match":
        return

    action = parts[1]
    if action == "propose" and len(parts) == 4:
        outcome = parts[2]
        try:
            match_id = int(parts[3])
        except ValueError:
            return
        result = propose_match_result(
            actor_telegram_id=update.effective_user.id,
            match_id=match_id,
            outcome=outcome,
            note_text=None,
        )
        if result.status != "proposed":
            await query.edit_message_text("Не удалось предложить результат для этого боя.")
            return
        await query.edit_message_text("Результат предложен.")
        await notify_match_result_proposed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
        return

    try:
        match_id = int(parts[2])
    except ValueError:
        return
    agree = action == "confirm"
    result = confirm_match_result(actor_telegram_id=update.effective_user.id, match_id=match_id, agree=agree)
    if result.status not in {"confirmed", "disputed"}:
        await query.edit_message_text("Не удалось обработать действие для этого боя.")
        return
    if agree:
        await query.edit_message_text("Результат подтвержден.")
        await notify_match_result_confirmed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    else:
        await query.edit_message_text("Бой отмечен как спорный.")
        await notify_match_result_disputed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)


async def confirm_result_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Введите ID боя, который хотите подтвердить.", reply_markup=cancel_keyboard())
    return ASK_CONFIRM_ID


async def dispute_result_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text("Введите ID боя, который хотите оспорить.", reply_markup=cancel_keyboard())
    return ASK_DISPUTE_ID


async def confirm_result_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finalize_result(update, context, agree=True)


async def dispute_result_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await _finalize_result(update, context, agree=False)


async def _finalize_result(update: Update, context: ContextTypes.DEFAULT_TYPE, agree: bool) -> int:
    user = update.effective_user
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_matches(update, context)
    try:
        match_id = int(text)
    except ValueError:
        await update.effective_message.reply_text("ID боя должен быть числом.", reply_markup=cancel_keyboard())
        return ASK_CONFIRM_ID if agree else ASK_DISPUTE_ID

    result = confirm_match_result(actor_telegram_id=user.id, match_id=match_id, agree=agree)
    if result.status == "missing":
        await update.effective_message.reply_text("Бой не найден.", reply_markup=matches_keyboard())
        return ConversationHandler.END
    if result.status == "forbidden":
        await update.effective_message.reply_text("Этот бой вам не принадлежит.", reply_markup=matches_keyboard())
        return ConversationHandler.END
    if result.status == "no_result":
        await update.effective_message.reply_text("По этому бою еще не предложен результат.", reply_markup=matches_keyboard())
        return ConversationHandler.END
    if result.status == "own_proposal":
        await update.effective_message.reply_text("Нельзя подтверждать собственное предложение результата.", reply_markup=matches_keyboard())
        return ConversationHandler.END

    if agree:
        await update.effective_message.reply_text("Результат подтвержден.", reply_markup=matches_keyboard())
        await notify_match_result_confirmed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    else:
        await update.effective_message.reply_text("Бой отмечен как спорный.", reply_markup=matches_keyboard())
        await notify_match_result_disputed(context, result.actor, result.other, result.match, result.winner, result.match.proposed_is_draw)
    return ConversationHandler.END


async def cancel_matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("match_flow", None)
    await update.effective_message.reply_text("Действие отменено.", reply_markup=matches_keyboard())
    return ConversationHandler.END
