from __future__ import annotations

from html import escape

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import (
    WEAPON_LABELS,
    WEAPON_TITLES,
    menu_keyboard_for_role,
    stats_keyboard,
    top_scope_keyboard,
    weapons_keyboard,
)
from bot.services.stats import get_top_ratings, get_user_stats, list_top_cities, list_top_schools


ASK_TOP_WEAPON, ASK_TOP_SCOPE, ASK_TOP_VALUE = range(80, 83)

TOP_SCOPE_LABELS = {
    "По городу": "city",
    "По школе": "school",
}


def _menu_keyboard(update: Update):
    user = update.effective_user
    settings = get_settings()
    return menu_keyboard_for_role(bool(user and user.id == settings.admin_telegram_id))


def _stats_text(stats) -> str:
    ratings_block = "\n".join(
        f"- {WEAPON_TITLES.get(weapon, weapon)}: {rating}" for weapon, rating in stats.ratings
    ) or "- Пока нет рейтингов"
    recent_block = "\n".join(
        f"- {item.completed_at:%Y-%m-%d}: {item.result} против {item.opponent_name} ({WEAPON_TITLES.get(item.weapon_type, item.weapon_type)})"
        for item in stats.recent
    ) or "- Пока нет завершенных боёв"
    return (
        "Статистика\n\n"
        f"Дата регистрации: {stats.registered_at:%Y-%m-%d}\n"
        f"Боев всего: {stats.total}\n"
        f"Победы: {stats.wins}\n"
        f"Поражения: {stats.losses}\n"
        f"Ничьи: {stats.draws}\n"
        f"Винрейт: {stats.win_rate}%\n\n"
        "Рейтинги:\n"
        f"{ratings_block}\n\n"
        "Последние 5 боёв:\n"
        f"{recent_block}"
    )


async def stats_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    if not user or not update.effective_message:
        return ConversationHandler.END
    stats = get_user_stats(user.id)
    if stats is None:
        await update.effective_message.reply_text("Сначала заполните профиль.", reply_markup=_menu_keyboard(update))
        return ConversationHandler.END
    await update.effective_message.reply_text(_stats_text(stats), reply_markup=stats_keyboard())
    return ConversationHandler.END


async def top_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if not update.effective_message:
        return ConversationHandler.END
    context.user_data.pop("top_flow", None)
    await update.effective_message.reply_text("Выберите оружие для топа.", reply_markup=weapons_keyboard(include_done=False))
    return ASK_TOP_WEAPON


async def top_weapon_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_stats(update, context)
    weapon_type = WEAPON_LABELS.get(text)
    if weapon_type is None:
        await update.effective_message.reply_text("Выберите оружие кнопкой.", reply_markup=weapons_keyboard(include_done=False))
        return ASK_TOP_WEAPON
    context.user_data["top_flow"] = {"weapon_type": weapon_type}
    await update.effective_message.reply_text("Какой топ показать?", reply_markup=top_scope_keyboard())
    return ASK_TOP_SCOPE


async def top_scope_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_stats(update, context)
    scope = TOP_SCOPE_LABELS.get(text)
    if scope is None:
        await update.effective_message.reply_text("Выберите вариант кнопкой.", reply_markup=top_scope_keyboard())
        return ASK_TOP_SCOPE

    options = list_top_cities() if scope == "city" else list_top_schools()
    context.user_data["top_flow"]["scope"] = scope
    context.user_data["top_flow"]["options"] = options

    if not options:
        label = "городов" if scope == "city" else "школ"
        await update.effective_message.reply_text(f"Пока нет доступных {label}.", reply_markup=stats_keyboard())
        context.user_data.pop("top_flow", None)
        return ConversationHandler.END

    prompt = "Выберите город" if scope == "city" else "Выберите школу"
    numbered_options = "\n".join(f"{index}. {item}" for index, item in enumerate(options, start=1))
    await update.effective_message.reply_text(
        f"{prompt}:\n\n{numbered_options}\n\nВведите номер.",
        reply_markup=top_scope_keyboard(),
    )
    return ASK_TOP_VALUE


async def top_value_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.effective_message.text if update.effective_message else "").strip()
    if text == "Отмена":
        return await cancel_stats(update, context)

    payload = context.user_data.get("top_flow", {})
    options = payload.get("options", [])
    try:
        selected_index = int(text)
    except ValueError:
        selected_index = None

    if selected_index is None or not 1 <= selected_index <= len(options):
        scope = payload.get("scope")
        prompt = "Выберите город" if scope == "city" else "Выберите школу"
        numbered_options = "\n".join(f"{index}. {item}" for index, item in enumerate(options, start=1))
        await update.effective_message.reply_text(
            f"{prompt}:\n\n{numbered_options}\n\nВведите номер из списка.",
            reply_markup=top_scope_keyboard(),
        )
        return ASK_TOP_VALUE

    text = options[selected_index - 1]
    weapon_type = payload["weapon_type"]
    scope = payload["scope"]
    entries = get_top_ratings(
        weapon_type=weapon_type,
        city=text if scope == "city" else None,
        school=text if scope == "school" else None,
        limit=20,
    )
    context.user_data.pop("top_flow", None)

    if not entries:
        await update.effective_message.reply_text("Для этого фильтра пока нет рейтинга.", reply_markup=stats_keyboard())
        return ConversationHandler.END

    title = f"Топ-20 по оружию <b>{escape(WEAPON_TITLES.get(weapon_type, weapon_type))}</b>"
    subtitle = f"Город: <b>{escape(text)}</b>" if scope == "city" else f"Школа: <b>{escape(text)}</b>"
    lines = [title, subtitle]
    for index, item in enumerate(entries, start=1):
        lines.append(
            f"\n{index}. <b>{escape(item.full_name)}</b>\n"
            f"Рейтинг: <b>{item.rating}</b>\n"
            f"Город: <b>{escape(item.city)}</b>\n"
            f"Школа: <b>{escape(item.school)}</b>"
        )
    await update.effective_message.reply_text("\n".join(lines), reply_markup=stats_keyboard())
    return ConversationHandler.END


async def cancel_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.pop("top_flow", None)
    if update.effective_message:
        await update.effective_message.reply_text("Действие отменено.", reply_markup=_menu_keyboard(update))
    return ConversationHandler.END
