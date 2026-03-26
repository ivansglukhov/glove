from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.keyboards.main import WEAPON_TITLES
from bot.services.stats import get_user_stats


async def stats_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.message:
        return
    stats = get_user_stats(user.id)
    if stats is None:
        await update.message.reply_text("Сначала заполните профиль.")
        return

    ratings_block = '\n'.join(
        f"- {WEAPON_TITLES.get(weapon, weapon)}: {rating}" for weapon, rating in stats.ratings
    ) or '- Пока нет рейтингов'
    recent_block = '\n'.join(
        f"- {item.completed_at:%Y-%m-%d}: {item.result} против {item.opponent_name} ({WEAPON_TITLES.get(item.weapon_type, item.weapon_type)})"
        for item in stats.recent
    ) or '- Пока нет завершенных боёв'

    text = (
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
    await update.message.reply_text(text)
