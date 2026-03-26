from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from bot.config import get_settings
from bot.keyboards.main import (
    READINESS_LABELS,
    READINESS_TITLES,
    WEAPON_LABELS,
    WEAPON_TITLES,
    cancel_keyboard,
    menu_keyboard_for_role,
    profile_keyboard,
    readiness_keyboard,
    weapons_keyboard,
)
from bot.services.notifications import notify_profile_saved, notify_statuses_updated
from bot.services.profile import get_user_by_telegram_id, upsert_user_profile, update_user_weapon_statuses


ASK_FULL_NAME, ASK_CITY, ASK_CLUB, ASK_WEAPONS, ASK_WEAPON_STATUS, ASK_STATUS_EDIT = range(6)


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    settings = get_settings()
    return bool(user and user.id == settings.admin_telegram_id)


def _display_name(update: Update) -> str | None:
    user = update.effective_user
    return user.full_name if user else None


def _profile_text(user) -> str:
    club_name = user.club.name if user.club else (user.custom_club_name or "Не указан")
    ratings = {rating.weapon_type: rating.rating_value for rating in user.ratings}
    weapon_lines = []
    for weapon in sorted(user.weapons, key=lambda item: item.weapon_type):
        title = WEAPON_TITLES.get(weapon.weapon_type, weapon.weapon_type)
        readiness = READINESS_TITLES.get(weapon.readiness_status, weapon.readiness_status)
        rating = ratings.get(weapon.weapon_type, "—")
        weapon_lines.append(f"- {title}: {readiness}, рейтинг {rating}")
    weapons_block = "\n".join(weapon_lines) if weapon_lines else "- Оружия пока не выбраны"
    return (
        "Ваш профиль:\n"
        f"Имя: {user.display_name or 'Не указано'}\n"
        f"ФИО: {user.full_name}\n"
        f"Город: {user.city}\n"
        f"Клуб: {club_name}\n"
        f"Дата регистрации: {user.registered_at:%Y-%m-%d}\n\n"
        "Оружия и статусы:\n"
        f"{weapons_block}"
    )


async def profile_entry(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return ConversationHandler.END

    user = get_user_by_telegram_id(tg_user.id)
    if user is None:
        await update.message.reply_text(
            "Профиль еще не заполнен. Давайте зарегистрируемся.\n\nВведите ваше ФИО.",
            reply_markup=cancel_keyboard(),
        )
        return ASK_FULL_NAME

    await update.message.reply_text(_profile_text(user), reply_markup=profile_keyboard(True))
    return ConversationHandler.END


async def register_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Введите ваше ФИО.", reply_markup=cancel_keyboard())
    return ASK_FULL_NAME


async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await cancel_profile(update, context)
    context.user_data["profile_form"] = {"full_name": text}
    await update.message.reply_text("Введите ваш город.", reply_markup=cancel_keyboard())
    return ASK_CITY


async def ask_club(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if not text or text == "Отмена":
        return await cancel_profile(update, context)
    context.user_data["profile_form"]["city"] = text
    await update.message.reply_text("Введите клуб. Если клуба нет, отправьте '-'.", reply_markup=cancel_keyboard())
    return ASK_CLUB


async def ask_weapons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_profile(update, context)
    context.user_data["profile_form"]["club_name"] = None if text == "-" else text
    context.user_data["selected_weapons"] = []
    await update.message.reply_text(
        "Выберите одно или несколько оружий. После выбора нажмите 'Готово'.",
        reply_markup=weapons_keyboard(),
    )
    return ASK_WEAPONS


async def collect_weapons(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_profile(update, context)

    selected = context.user_data.setdefault("selected_weapons", [])
    if text == "Готово":
        if not selected:
            await update.message.reply_text("Нужно выбрать хотя бы одно оружие.", reply_markup=weapons_keyboard())
            return ASK_WEAPONS
        context.user_data["weapon_statuses"] = []
        context.user_data["weapon_index"] = 0
        weapon_title = WEAPON_TITLES[selected[0]]
        await update.message.reply_text(
            f"Укажите статус готовности для оружия '{weapon_title}'.",
            reply_markup=readiness_keyboard(),
        )
        return ASK_WEAPON_STATUS

    weapon_type = WEAPON_LABELS.get(text)
    if weapon_type is None:
        await update.message.reply_text("Выберите оружие кнопкой.", reply_markup=weapons_keyboard())
        return ASK_WEAPONS

    if weapon_type not in selected:
        selected.append(weapon_type)
    pretty = ", ".join(WEAPON_TITLES[item] for item in selected)
    await update.message.reply_text(f"Выбрано: {pretty}", reply_markup=weapons_keyboard())
    return ASK_WEAPONS


async def collect_weapon_statuses(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_profile(update, context)
    readiness = READINESS_LABELS.get(text)
    if readiness is None:
        await update.message.reply_text("Выберите статус кнопкой.", reply_markup=readiness_keyboard())
        return ASK_WEAPON_STATUS

    selected = context.user_data["selected_weapons"]
    weapon_index = context.user_data["weapon_index"]
    context.user_data["weapon_statuses"].append(
        {"weapon_type": selected[weapon_index], "readiness_status": readiness}
    )
    weapon_index += 1
    context.user_data["weapon_index"] = weapon_index

    if weapon_index >= len(selected):
        return await finish_profile(update, context)

    next_weapon = WEAPON_TITLES[selected[weapon_index]]
    await update.message.reply_text(
        f"Укажите статус готовности для оружия '{next_weapon}'.",
        reply_markup=readiness_keyboard(),
    )
    return ASK_WEAPON_STATUS


async def finish_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    form = context.user_data.get("profile_form", {})
    tg_user = update.effective_user
    existing_user = get_user_by_telegram_id(tg_user.id)
    user = upsert_user_profile(
        telegram_id=tg_user.id,
        username=tg_user.username,
        display_name=_display_name(update),
        full_name=form["full_name"],
        city=form["city"],
        club_name=form.get("club_name"),
        weapons=context.user_data.get("weapon_statuses", []),
    )
    context.user_data.clear()
    await update.message.reply_text(
        "Профиль сохранен.\n\n" + _profile_text(user),
        reply_markup=profile_keyboard(True),
    )
    await notify_profile_saved(context, user, is_new=existing_user is None)
    return ConversationHandler.END


async def edit_statuses_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_user = update.effective_user
    if not tg_user or not update.message:
        return ConversationHandler.END
    user = get_user_by_telegram_id(tg_user.id)
    if user is None or not user.weapons:
        await update.message.reply_text("Сначала зарегистрируйтесь и добавьте оружие.")
        return ConversationHandler.END

    context.user_data["selected_weapons"] = [weapon.weapon_type for weapon in sorted(user.weapons, key=lambda item: item.weapon_type)]
    context.user_data["weapon_statuses"] = []
    context.user_data["weapon_index"] = 0
    current_weapon = WEAPON_TITLES[context.user_data["selected_weapons"][0]]
    await update.message.reply_text(
        f"Обновляем статусы. Укажите статус для '{current_weapon}'.",
        reply_markup=readiness_keyboard(),
    )
    return ASK_STATUS_EDIT


async def collect_status_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text if update.message else "").strip()
    if text == "Отмена":
        return await cancel_profile(update, context)
    readiness = READINESS_LABELS.get(text)
    if readiness is None:
        await update.message.reply_text("Выберите статус кнопкой.", reply_markup=readiness_keyboard())
        return ASK_STATUS_EDIT

    selected = context.user_data["selected_weapons"]
    weapon_index = context.user_data["weapon_index"]
    context.user_data["weapon_statuses"].append(
        {"weapon_type": selected[weapon_index], "readiness_status": readiness}
    )
    weapon_index += 1
    context.user_data["weapon_index"] = weapon_index

    if weapon_index >= len(selected):
        tg_user = update.effective_user
        user = update_user_weapon_statuses(tg_user.id, context.user_data["weapon_statuses"])
        context.user_data.clear()
        await update.message.reply_text(
            "Статусы обновлены.\n\n" + _profile_text(user),
            reply_markup=profile_keyboard(True),
        )
        await notify_statuses_updated(context, user)
        return ConversationHandler.END

    next_weapon = WEAPON_TITLES[selected[weapon_index]]
    await update.message.reply_text(
        f"Укажите статус для '{next_weapon}'.",
        reply_markup=readiness_keyboard(),
    )
    return ASK_STATUS_EDIT


async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    await update.message.reply_text(
        "Действие отменено.",
        reply_markup=menu_keyboard_for_role(_is_admin(update)),
    )
    return ConversationHandler.END
