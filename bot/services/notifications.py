from __future__ import annotations

from html import escape

from telegram import InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.config import get_settings
from bot.keyboards.main import READINESS_TITLES, WEAPON_TITLES, invitation_actions_inline, mail_actions_inline, match_actions_inline
from bot.services.profile import get_user_by_telegram_id


def _public_name(user) -> str:
    return user.full_name


def _club_text(user) -> str:
    return user.club.name if user.club else (user.custom_club_name or "Не указан")


def _mail_actor_line(user) -> str:
    profile = get_user_by_telegram_id(user.telegram_id)
    if profile is not None:
        return f"{_public_name(profile)}({_club_text(profile)})"
    return f"{_public_name(user)}({getattr(user, 'custom_club_name', None) or 'Не указан'})"


def _weapon_block_with_ratings(user) -> str:
    ratings = {rating.weapon_type: rating.rating_value for rating in user.ratings}
    lines = []
    for weapon in sorted(user.weapons, key=lambda item: item.weapon_type):
        lines.append(
            f"- {WEAPON_TITLES.get(weapon.weapon_type, weapon.weapon_type)}: "
            f"{READINESS_TITLES.get(weapon.readiness_status, weapon.readiness_status)}, "
            f"рейтинг {ratings.get(weapon.weapon_type, '—')}"
        )
    return "\n".join(lines) if lines else "- Не выбраны"


def _weapon_block_statuses(user) -> str:
    lines = []
    for weapon in sorted(user.weapons, key=lambda item: item.weapon_type):
        lines.append(
            f"- {WEAPON_TITLES.get(weapon.weapon_type, weapon.weapon_type)}: "
            f"{READINESS_TITLES.get(weapon.readiness_status, weapon.readiness_status)}"
        )
    return "\n".join(lines) if lines else "- Не выбраны"


def _result_text(winner, is_draw: bool) -> str:
    if is_draw:
        return "ничья"
    return f"победа {winner.full_name}" if winner else "результат не указан"


def _actor_line(user) -> str:
    return f"{_public_name(user)} ({user.telegram_id})"


async def send_admin_message(context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    settings = get_settings()
    if not settings.admin_telegram_id:
        return False
    try:
        await context.bot.send_message(chat_id=settings.admin_telegram_id, text=text)
        return True
    except TelegramError:
        return False


async def send_user_message(
    context: ContextTypes.DEFAULT_TYPE,
    telegram_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    photo_file_id: str | None = None,
    sticker_file_id: str | None = None,
) -> bool:
    try:
        if photo_file_id:
            await context.bot.send_photo(
                chat_id=telegram_id,
                photo=photo_file_id,
                caption=text,
                reply_markup=reply_markup,
            )
        elif sticker_file_id:
            if text:
                await context.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
                await context.bot.send_sticker(chat_id=telegram_id, sticker=sticker_file_id)
            else:
                await context.bot.send_sticker(chat_id=telegram_id, sticker=sticker_file_id, reply_markup=reply_markup)
        else:
            await context.bot.send_message(chat_id=telegram_id, text=text, reply_markup=reply_markup)
        return True
    except TelegramError:
        return False


async def notify_profile_saved(context: ContextTypes.DEFAULT_TYPE, user, is_new: bool) -> bool:
    event_title = "Новая регистрация" if is_new else "Профиль обновлен"
    text = (
        f"{event_title}\n\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"ФИО: {user.full_name}\n"
        f"Город: {user.city}\n"
        f"Клуб: {_club_text(user)}\n"
        "Оружия:\n"
        f"{_weapon_block_with_ratings(user)}"
    )
    return await send_admin_message(context, text)


async def notify_statuses_updated(context: ContextTypes.DEFAULT_TYPE, user) -> bool:
    text = (
        "Статусы обновлены\n\n"
        f"Telegram ID: {user.telegram_id}\n"
        f"ФИО: {user.full_name}\n"
        f"Город: {user.city}\n"
        f"Клуб: {_club_text(user)}\n"
        "Оружия и статусы:\n"
        f"{_weapon_block_statuses(user)}"
    )
    return await send_admin_message(context, text)


async def notify_invitation_created(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, invitation) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    inviter_text = (
        f"Перчатка брошена.\n\n"
        f"Кому: {_public_name(invitee)}\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}"
    )
    invitee_text = (
        "Вам бросили перчатку.\n\n"
        f"От: {_public_name(inviter)}\n"
        f"Клуб: {_club_text(inviter)}\n"
        f"Город: {inviter.city}\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}\n\n"
        "Пройдите в перчаточную, чтобы принять перчатку или вернуть ее."
    )
    admin_text = (
        f"{_actor_line(inviter)} 🥊 {invitation.id} 🥊 {_actor_line(invitee)}"
    )
    await send_user_message(context, inviter.telegram_id, inviter_text)
    await send_user_message(
        context,
        invitee.telegram_id,
        invitee_text,
        reply_markup=invitation_actions_inline(invitation.id),
    )
    await send_admin_message(context, admin_text)


async def notify_external_invitation_created(context: ContextTypes.DEFAULT_TYPE, inviter, invitation, bot_username: str | None) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    deeplink = f"https://t.me/{bot_username}?start=invite_{invitation.id}" if bot_username else "Ссылка будет доступна после запуска бота"
    inviter_text = (
        "Пользователь не найден среди зарегистрированных.\n\n"
        f"Цель: {invitation.invitee_external_text}\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}\n"
        f"Отправьте ему эту ссылку: {deeplink}"
    )
    admin_text = (
        "Внешняя перчатка\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"От: {_public_name(inviter)} ({inviter.telegram_id})\n"
        f"Кому: {invitation.invitee_external_text}\n"
        f"Оружие: {weapon}"
    )
    await send_user_message(context, inviter.telegram_id, inviter_text)
    await send_admin_message(context, admin_text)


async def notify_invitation_response(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, invitation, accepted: bool) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    status_text = "принял перчатку" if accepted else "вернул перчатку"
    inviter_text = (
        f"Пользователь {_public_name(invitee)} {status_text}.\n\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}"
    )
    invitee_text = (
        f"Ваш ответ сохранен: {'перчатка принята' if accepted else 'перчатка возвращена'}.\n\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}"
    )
    admin_text = (
        f"Ответ на перчатку\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"Статус: {'accepted' if accepted else 'declined'}\n"
        f"От: {_public_name(inviter)} ({inviter.telegram_id})\n"
        f"Кем обработано: {_public_name(invitee)} ({invitee.telegram_id})\n"
        f"Оружие: {weapon}"
    )
    await send_user_message(context, inviter.telegram_id, inviter_text)
    await send_user_message(context, invitee.telegram_id, invitee_text)
    await send_admin_message(context, admin_text)


async def notify_invitation_cancelled(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, invitation) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    inviter_text = (
        "Вы забрали перчатку.\n\n"
        f"Оружие: {weapon}\n"
        f"ID перчатки: {invitation.id}"
    )
    admin_text = (
        "Перчатка забрана\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"От: {_public_name(inviter)} ({inviter.telegram_id})\n"
        f"Оружие: {weapon}"
    )
    await send_user_message(context, inviter.telegram_id, inviter_text)
    if invitee is not None:
        invitee_text = (
            "Соперник забрал перчатку.\n\n"
            f"Оружие: {weapon}\n"
            f"ID перчатки: {invitation.id}"
        )
        await send_user_message(context, invitee.telegram_id, invitee_text)
        admin_text += f"\nКому: {_public_name(invitee)} ({invitee.telegram_id})"
    elif invitation.invitee_external_text:
        admin_text += f"\nКому: {invitation.invitee_external_text}"
    await send_admin_message(context, admin_text)


async def notify_match_created(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, match) -> None:
    weapon = WEAPON_TITLES.get(match.weapon_type, match.weapon_type)
    text = (
        "Бой создан.\n\n"
        f"ID боя: {match.id}\n"
        f"Соперник: {_public_name(invitee)}\n"
        f"Оружие: {weapon}\n\n"
        "После спарринга зайдите в раздел 'Мои бои' и предложите результат."
    )
    other_text = (
        "Бой создан.\n\n"
        f"ID боя: {match.id}\n"
        f"Соперник: {_public_name(inviter)}\n"
        f"Оружие: {weapon}\n\n"
        "После спарринга зайдите в раздел 'Мои бои' и предложите результат."
    )
    admin_text = (
        f"{_actor_line(inviter)} ⚔️ {match.id} ⚔️ {_actor_line(invitee)}"
    )
    result_markup = match_actions_inline(match.id, can_propose=True, can_confirm=False)
    await send_user_message(context, inviter.telegram_id, text, reply_markup=result_markup)
    await send_user_message(context, invitee.telegram_id, other_text, reply_markup=result_markup)
    await send_admin_message(context, admin_text)


async def notify_match_result_proposed(context: ContextTypes.DEFAULT_TYPE, actor, other, match, winner, is_draw: bool) -> None:
    result_text = _result_text(winner, is_draw)
    weapon = WEAPON_TITLES.get(match.weapon_type, match.weapon_type)
    actor_text = (
        "Результат боя предложен.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Результат: {result_text}"
    )
    other_text = (
        "По вашему бою предложен результат.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Результат: {result_text}\n\n"
        "Зайдите в раздел 'Мои бои', чтобы подтвердить или оспорить результат."
    )
    admin_text = (
        "Предложен результат боя\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Кто предложил: {_public_name(actor)} ({actor.telegram_id})\n"
        f"Результат: {result_text}"
    )
    await send_user_message(context, actor.telegram_id, actor_text)
    await send_user_message(context, other.telegram_id, other_text)
    await send_admin_message(context, admin_text)


async def notify_match_result_confirmed(context: ContextTypes.DEFAULT_TYPE, actor, other, match, winner, is_draw: bool) -> None:
    result_text = _result_text(winner, is_draw)
    weapon = WEAPON_TITLES.get(match.weapon_type, match.weapon_type)
    text = (
        "Результат боя подтвержден.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Результат: {result_text}"
    )
    admin_text = (
        "Бой завершен\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Результат: {result_text}\n"
        f"Подтвердил: {_public_name(actor)} ({actor.telegram_id})"
    )
    await send_user_message(context, actor.telegram_id, text)
    await send_user_message(context, other.telegram_id, text)
    await send_admin_message(context, admin_text)


async def notify_match_result_disputed(context: ContextTypes.DEFAULT_TYPE, actor, other, match, winner, is_draw: bool) -> None:
    result_text = _result_text(winner, is_draw)
    weapon = WEAPON_TITLES.get(match.weapon_type, match.weapon_type)
    actor_text = (
        "Результат боя оспорен.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Предложенный результат: {result_text}"
    )
    other_text = (
        "Ваш результат боя оспорен.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        "Можно подать жалобу, а пока бой отмечен как спорный."
    )
    admin_text = (
        "Спорный бой\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}\n"
        f"Предложенный результат: {result_text}\n"
        f"Оспорил: {_public_name(actor)} ({actor.telegram_id})"
    )
    await send_user_message(context, actor.telegram_id, actor_text)
    await send_user_message(context, other.telegram_id, other_text)
    await send_admin_message(context, admin_text)


async def notify_complaint_created(context: ContextTypes.DEFAULT_TYPE, from_telegram_id: int, complaint) -> None:
    user = get_user_by_telegram_id(from_telegram_id)
    if user is None:
        return
    text = (
        "Новая жалоба\n\n"
        f"ID жалобы: {complaint.id}\n"
        f"От: {user.full_name} ({user.telegram_id})\n"
        f"Match ID: {complaint.match_id or '—'}\n"
        f"Текст: {complaint.text}"
    )
    await send_admin_message(context, text)


async def notify_suggestion_created(context: ContextTypes.DEFAULT_TYPE, from_telegram_id: int, suggestion) -> None:
    user = get_user_by_telegram_id(from_telegram_id)
    if user is None:
        return
    text = (
        "Новое предложение\n\n"
        f"ID предложения: {suggestion.id}\n"
        f"От: {user.full_name} ({user.telegram_id})\n"
        f"Текст: {suggestion.text}"
    )
    await send_admin_message(context, text)


async def notify_mail_received(context: ContextTypes.DEFAULT_TYPE, sender, recipient, message) -> None:
    sender_name = "Ваша любимая администрация" if getattr(sender, "is_admin", False) else sender.full_name
    text = (
        f"курлык, у вас новый голубь от {escape(sender_name)}\n\n"
        f"ID сообщения: {message.id}"
    )
    if message.text:
        text += f"\n\n{escape(message.text)}"
    await send_user_message(
        context,
        recipient.telegram_id,
        text,
        reply_markup=mail_actions_inline(message.id),
        photo_file_id=message.photo_file_id,
        sticker_file_id=message.sticker_file_id,
    )
    if not getattr(sender, "is_admin", False) and not getattr(recipient, "is_admin", False):
        admin_text = (
            "Сообщение:\n"
            f"{_mail_actor_line(sender)} -> {_mail_actor_line(recipient)}"
        )
        if message.text:
            admin_text += f"\n\n{message.text}"
        await send_admin_message(context, admin_text)


async def notify_invitation_expired(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, invitation) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    text = f"Перчатка {invitation.id} истекла. Оружие: {weapon}."
    await send_user_message(context, inviter.telegram_id, text)
    if invitee is not None:
        await send_user_message(context, invitee.telegram_id, text)
    await send_admin_message(context, f"Истекла перчатка {invitation.id}. Оружие: {weapon}.")


async def notify_match_auto_draw(context: ContextTypes.DEFAULT_TYPE, fighter_a, fighter_b, match) -> None:
    weapon = WEAPON_TITLES.get(match.weapon_type, match.weapon_type)
    text = (
        "Бой автоматически завершен ничьей из-за отсутствия подтверждения в течение 7 дней.\n\n"
        f"ID боя: {match.id}\n"
        f"Оружие: {weapon}"
    )
    await send_user_message(context, fighter_a.telegram_id, text)
    await send_user_message(context, fighter_b.telegram_id, text)
    await send_admin_message(context, f"Бой {match.id} автоматически завершен ничьей. Оружие: {weapon}.")


async def notify_admin_ping(context: ContextTypes.DEFAULT_TYPE, requester_id: int) -> bool:
    return await send_admin_message(context, f"Тест канала админ-уведомлений от пользователя {requester_id}.")

async def notify_external_invitation_linked(context: ContextTypes.DEFAULT_TYPE, inviter, invitee, invitation) -> None:
    weapon = WEAPON_TITLES.get(invitation.weapon_type, invitation.weapon_type)
    inviter_text = (
        "Ваша внешняя перчатка привязана к зарегистрированному пользователю.\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"Кто принял ссылку: {_public_name(invitee)} ({invitee.telegram_id})\n"
        f"Оружие: {weapon}"
    )
    invitee_text = (
        "Вы подключились по ссылке перчатки.\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"От: {_public_name(inviter)}\n"
        f"Оружие: {weapon}\n\n"
        "Пройдите в перчаточную, чтобы принять перчатку или вернуть ее."
    )
    admin_text = (
        "Внешняя перчатка привязана\n\n"
        f"ID перчатки: {invitation.id}\n"
        f"От: {_public_name(inviter)} ({inviter.telegram_id})\n"
        f"Кому: {_public_name(invitee)} ({invitee.telegram_id})\n"
        f"Оружие: {weapon}"
    )
    await send_user_message(context, inviter.telegram_id, inviter_text)
    await send_user_message(context, invitee.telegram_id, invitee_text)
    await send_admin_message(context, admin_text)
