from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db import session_scope
from bot.models import MailMessage, User


@dataclass(slots=True)
class MailRecipientView:
    telegram_id: int
    full_name: str
    city: str
    club_name: str


@dataclass(slots=True)
class MailMessageView:
    message_id: int
    sender_name: str
    text: str
    created_at: object


def _display_name(user: User) -> str:
    if user.is_admin:
        return "Ваша любимая администрация"
    return user.full_name


def _club_name(user: User) -> str:
    return user.club.name if user.club else (user.custom_club_name or "Без клуба")


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
        if requester is not None and club_name is None and not own_club_only:
            stmt = stmt.where(User.city == requester.city)
        users = session.execute(stmt).scalars().all()

        if own_club_only:
            if requester is None:
                return []
            if requester.club_id is not None:
                users = [user for user in users if user.club_id == requester.club_id]
            elif requester.custom_club_name:
                normalized = requester.custom_club_name.strip().lower()
                users = [user for user in users if _club_name(user).strip().lower() == normalized]
            else:
                users = []
        elif club_name:
            normalized = club_name.strip().lower()
            users = [user for user in users if _club_name(user).strip().lower() == normalized]

        users.sort(key=lambda item: (_club_name(item).lower(), item.city.lower(), item.full_name.lower()))
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
    query = f"%{full_name_query.strip()}%"
    with session_scope() as session:
        users = session.execute(
            select(User)
            .where(User.full_name.ilike(query), User.is_active.is_(True))
            .options(selectinload(User.club))
            .order_by(User.full_name.asc())
        ).scalars().all()
        return [_recipient_view(user) for user in users]


def create_mail_message(*, from_telegram_id: int, to_telegram_id: int, text: str) -> tuple[MailMessage | None, User | None, User | None]:
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
        message = MailMessage(from_user_id=sender.id, to_user_id=recipient.id, text=text.strip())
        session.add(message)
        session.flush()
        session.refresh(message)
        return message, sender, recipient


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
                    sender_name=_display_name(sender),
                    text=item.text,
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
