from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db import session_scope
from bot.models import MailMessage, User
from bot.services.profile import normalize_city_name, normalize_club_name


@dataclass(slots=True)
class MailRecipientView:
    telegram_id: int
    full_name: str
    city: str
    club_name: str


@dataclass(slots=True)
class MailMessageView:
    message_id: int
    sender_telegram_id: int
    sender_name: str
    text: str
    photo_file_id: str | None
    sticker_file_id: str | None
    recipient_name: str
    created_at: object


def _display_name(user: User) -> str:
    if user.is_admin:
        return "Ваша любимая администрация"
    return user.full_name


def _club_name(user: User) -> str:
    raw_name = user.club.name if user.club else user.custom_club_name
    return normalize_club_name(raw_name) or "Без клуба"


def _recipient_view(user: User) -> MailRecipientView:
    return MailRecipientView(
        telegram_id=user.telegram_id,
        full_name=user.full_name,
        city=user.city,
        club_name=_club_name(user),
    )


def search_mail_recipients_by_filters(
    *,
    requester_telegram_id: int,
    own_club_only: bool = False,
    club_name: str | None = None,
    city_name: str | None = None,
) -> list[MailRecipientView]:
    with session_scope() as session:
        requester = session.execute(
            select(User)
            .where(User.telegram_id == requester_telegram_id, User.is_active.is_(True))
            .options(selectinload(User.club))
        ).scalar_one_or_none()
        if requester is None and club_name is None and not own_club_only:
            return []

        stmt = select(User).where(User.is_active.is_(True), User.telegram_id != requester_telegram_id).options(selectinload(User.club))
        users = session.execute(stmt).scalars().all()

        if requester is not None and club_name is None and not own_club_only:
            requester_city = normalize_city_name(city_name or requester.city)
            users = [user for user in users if normalize_city_name(user.city) == requester_city]

        if own_club_only:
            if requester is None:
                return []
            if requester.club_id is not None:
                users = [user for user in users if user.club_id == requester.club_id]
            elif requester.custom_club_name:
                normalized = normalize_club_name(requester.custom_club_name)
                users = [user for user in users if _club_name(user) == normalized]
            else:
                users = []
        elif club_name:
            normalized = normalize_club_name(club_name)
            users = [user for user in users if _club_name(user) == normalized]

        users.sort(key=lambda item: (_club_name(item).casefold(), item.city.casefold(), item.full_name.casefold()))
        return [_recipient_view(user) for user in users]


def search_mail_recipients_by_username(*, username: str) -> list[MailRecipientView]:
    normalized = username.lstrip("@").strip()
    with session_scope() as session:
        users = session.execute(
            select(User)
            .where(func.lower(User.username) == normalized.lower(), User.is_active.is_(True))
            .options(selectinload(User.club))
        ).scalars().all()
        return [_recipient_view(user) for user in users]


def search_mail_recipients_by_full_name(*, full_name_query: str) -> list[MailRecipientView]:
    normalized_query = full_name_query.strip().casefold()
    if not normalized_query:
        return []
    with session_scope() as session:
        users = [
            user
            for user in session.execute(
                select(User)
                .where(User.is_active.is_(True))
                .options(selectinload(User.club))
                .order_by(User.full_name.asc())
            ).scalars().all()
            if normalized_query in user.full_name.casefold()
        ]
        return [_recipient_view(user) for user in users]


def create_mail_message(
    *,
    from_telegram_id: int,
    to_telegram_id: int,
    text: str,
    photo_file_id: str | None = None,
    sticker_file_id: str | None = None,
) -> tuple[MailMessage | None, User | None, User | None]:
    with session_scope() as session:
        sender = session.execute(select(User).where(User.telegram_id == from_telegram_id)).scalar_one_or_none()
        settings = get_settings()
        if sender is None and from_telegram_id == settings.admin_telegram_id:
            sender = User(
                telegram_id=from_telegram_id,
                full_name="Ваша любимая администрация",
                city="Система",
                is_admin=True,
                is_active=True,
            )
            session.add(sender)
            session.flush()
        recipient = session.execute(select(User).where(User.telegram_id == to_telegram_id)).scalar_one_or_none()
        if sender is None or recipient is None or sender.id == recipient.id:
            return None, sender, recipient
        message = MailMessage(
            from_user_id=sender.id,
            to_user_id=recipient.id,
            text=text.strip(),
            photo_file_id=photo_file_id,
            sticker_file_id=sticker_file_id,
            broadcast_key=None,
        )
        session.add(message)
        session.flush()
        session.refresh(message)
        return message, sender, recipient


def create_mail_broadcast(
    *,
    from_telegram_id: int,
    text: str,
    photo_file_id: str | None = None,
    sticker_file_id: str | None = None,
) -> tuple[User | None, list[tuple[MailMessage, User]]]:
    with session_scope() as session:
        sender = session.execute(select(User).where(User.telegram_id == from_telegram_id)).scalar_one_or_none()
        settings = get_settings()
        if sender is None and from_telegram_id == settings.admin_telegram_id:
            sender = User(
                telegram_id=from_telegram_id,
                full_name="Ваша любимая администрация",
                city="Система",
                is_admin=True,
                is_active=True,
            )
            session.add(sender)
            session.flush()
        if sender is None:
            return None, []

        recipients = session.execute(
            select(User)
            .where(User.is_active.is_(True), User.telegram_id != from_telegram_id)
            .order_by(User.id.asc())
        ).scalars().all()

        created: list[tuple[MailMessage, User]] = []
        message_text = text.strip()
        broadcast_key = uuid.uuid4().hex
        for recipient in recipients:
            message = MailMessage(
                from_user_id=sender.id,
                to_user_id=recipient.id,
                text=message_text,
                photo_file_id=photo_file_id,
                sticker_file_id=sticker_file_id,
                broadcast_key=broadcast_key,
            )
            session.add(message)
            created.append((message, recipient))

        session.flush()
        return sender, created


def list_incoming_mail(*, recipient_telegram_id: int) -> list[MailMessageView]:
    with session_scope() as session:
        recipient = session.execute(select(User).where(User.telegram_id == recipient_telegram_id)).scalar_one_or_none()
        if recipient is None:
            return []
        items = session.execute(
            select(MailMessage)
            .where(
                MailMessage.to_user_id == recipient.id,
                MailMessage.is_deleted_by_recipient.is_(False),
            )
            .order_by(MailMessage.created_at.desc())
        ).scalars().all()
        result = []
        for item in items:
            sender = session.execute(select(User).where(User.id == item.from_user_id)).scalar_one()
            result.append(
                MailMessageView(
                    message_id=item.id,
                    sender_telegram_id=sender.telegram_id,
                    sender_name=_display_name(sender),
                    text=item.text,
                    photo_file_id=item.photo_file_id,
                    sticker_file_id=item.sticker_file_id,
                    recipient_name="",
                    created_at=item.created_at,
                )
            )
        return result


def list_outgoing_mail(*, sender_telegram_id: int) -> list[MailMessageView]:
    with session_scope() as session:
        sender = session.execute(select(User).where(User.telegram_id == sender_telegram_id)).scalar_one_or_none()
        if sender is None:
            return []
        items = session.execute(
            select(MailMessage)
            .where(MailMessage.from_user_id == sender.id)
            .order_by(MailMessage.created_at.desc(), MailMessage.id.desc())
        ).scalars().all()

        result: list[MailMessageView] = []
        seen_broadcasts: set[str] = set()
        for item in items:
            if item.broadcast_key:
                if item.broadcast_key in seen_broadcasts:
                    continue
                seen_broadcasts.add(item.broadcast_key)
                recipient_name = "всем"
            else:
                recipient = session.execute(select(User).where(User.id == item.to_user_id)).scalar_one()
                recipient_name = _display_name(recipient)
            result.append(
                MailMessageView(
                    message_id=item.id,
                    sender_telegram_id=sender.telegram_id,
                    sender_name=_display_name(sender),
                    text=item.text,
                    photo_file_id=item.photo_file_id,
                    sticker_file_id=item.sticker_file_id,
                    recipient_name=recipient_name,
                    created_at=item.created_at,
                )
            )
        return result


def delete_incoming_mail(*, recipient_telegram_id: int, message_id: int) -> bool:
    with session_scope() as session:
        recipient = session.execute(select(User).where(User.telegram_id == recipient_telegram_id)).scalar_one_or_none()
        if recipient is None:
            return False
        item = session.execute(
            select(MailMessage).where(MailMessage.id == message_id, MailMessage.to_user_id == recipient.id)
        ).scalar_one_or_none()
        if item is None:
            return False
        item.is_deleted_by_recipient = True
        session.flush()
        return True
