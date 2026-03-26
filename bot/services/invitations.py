from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select

from bot.config import get_settings
from bot.db import session_scope
from bot.enums import InvitationStatus
from bot.models import Invitation, User
from bot.services.matches import create_match_from_invitation


@dataclass(slots=True)
class InvitationView:
    invitation_id: int
    direction: str
    status: str
    weapon_type: str
    created_at: datetime
    expires_at: datetime
    other_name: str
    other_telegram_id: int | None
    other_username: str | None
    is_external: bool
    external_text: str | None


@dataclass(slots=True)
class InvitationCreateResult:
    status: str
    invitation: Invitation | None = None
    invitee: User | None = None
    matches: list[User] | None = None
    external_text: str | None = None


@dataclass(slots=True)
class InvitationResponseResult:
    status: str
    invitation: Invitation | None = None
    inviter: User | None = None
    invitee: User | None = None
    match: object | None = None


@dataclass(slots=True)
class ExpiredInvitationRecord:
    invitation: Invitation
    inviter: User
    invitee: User | None


def _is_broken_text(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
    if not text:
        return True
    visible = [char for char in text if not char.isspace()]
    if not visible:
        return True
    broken = sum(char in {"?", "\ufffd"} for char in visible)
    return broken / len(visible) >= 0.4


def _display_name(user: User) -> str:
    for candidate in (user.full_name, user.display_name, user.username):
        if not _is_broken_text(candidate):
            return candidate.strip()
    return "Пользователь"


def resolve_target(identifier: str) -> InvitationCreateResult:
    raw = identifier.strip()
    with session_scope() as session:
        users = []
        if raw.isdigit():
            stmt = select(User).where(User.telegram_id == int(raw), User.is_active.is_(True))
            users = session.execute(stmt).scalars().all()
        elif raw.startswith("@"):
            stmt = select(User).where(User.username.ilike(raw.lstrip("@")), User.is_active.is_(True))
            users = session.execute(stmt).scalars().all()
        else:
            stmt = (
                select(User)
                .where(User.full_name.ilike(f"%{raw}%"), User.is_active.is_(True))
                .order_by(User.full_name.asc())
            )
            users = session.execute(stmt).scalars().all()

        if len(users) == 1:
            return InvitationCreateResult(status="resolved", invitee=users[0])
        if len(users) > 1:
            return InvitationCreateResult(status="ambiguous", matches=users)
        return InvitationCreateResult(status="external", external_text=raw)


def create_invitation(*, inviter_telegram_id: int, weapon_type: str, target_text: str) -> InvitationCreateResult:
    target = resolve_target(target_text)
    settings = get_settings()
    expires_at = datetime.utcnow() + timedelta(days=settings.invitation_ttl_days)

    with session_scope() as session:
        inviter = session.execute(select(User).where(User.telegram_id == inviter_telegram_id)).scalar_one_or_none()
        if inviter is None:
            return InvitationCreateResult(status="inviter_missing")

        if target.status == "resolved" and target.invitee is not None:
            if target.invitee.telegram_id == inviter_telegram_id:
                return InvitationCreateResult(status="self_invite")
            invitation = Invitation(
                inviter_user_id=inviter.id,
                invitee_user_id=target.invitee.id,
                weapon_type=weapon_type,
                status=InvitationStatus.PENDING.value,
                expires_at=expires_at,
            )
            session.add(invitation)
            session.flush()
            session.refresh(invitation)
            return InvitationCreateResult(status="created", invitation=invitation, invitee=target.invitee)

        if target.status == "ambiguous":
            return target

        invitation = Invitation(
            inviter_user_id=inviter.id,
            invitee_external_text=target.external_text,
            weapon_type=weapon_type,
            status=InvitationStatus.PENDING.value,
            expires_at=expires_at,
        )
        session.add(invitation)
        session.flush()
        session.refresh(invitation)
        return InvitationCreateResult(status="external_created", invitation=invitation, external_text=target.external_text)


def list_invitations(*, telegram_id: int, incoming: bool) -> list[InvitationView]:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user is None:
            return []

        condition = Invitation.invitee_user_id == user.id if incoming else Invitation.inviter_user_id == user.id
        invitations = session.execute(select(Invitation).where(condition).order_by(Invitation.created_at.desc())).scalars().all()
        result = []
        for item in invitations:
            inviter = session.execute(select(User).where(User.id == item.inviter_user_id)).scalar_one_or_none()
            invitee = (
                session.execute(select(User).where(User.id == item.invitee_user_id)).scalar_one_or_none()
                if item.invitee_user_id
                else None
            )
            other = inviter if incoming else invitee
            result.append(
                InvitationView(
                    invitation_id=item.id,
                    direction="incoming" if incoming else "outgoing",
                    status=item.status,
                    weapon_type=item.weapon_type,
                    created_at=item.created_at,
                    expires_at=item.expires_at,
                    other_name=(
                        _display_name(other)
                        if other
                        else (
                            item.invitee_external_text.strip()
                            if not _is_broken_text(item.invitee_external_text)
                            else "Внешний пользователь"
                        )
                    ),
                    other_telegram_id=other.telegram_id if other else None,
                    other_username=other.username if other else None,
                    is_external=item.invitee_user_id is None,
                    external_text=item.invitee_external_text,
                )
            )
        return result


def get_pending_invitation_for_user(*, invitation_id: int, user_telegram_id: int) -> InvitationResponseResult:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == user_telegram_id)).scalar_one_or_none()
        if user is None:
            return InvitationResponseResult(status="invitee_missing")
        invitation = session.execute(select(Invitation).where(Invitation.id == invitation_id)).scalar_one_or_none()
        if invitation is None:
            return InvitationResponseResult(status="missing")
        inviter = session.execute(select(User).where(User.id == invitation.inviter_user_id)).scalar_one_or_none()

        if invitation.invitee_user_id != user.id:
            return InvitationResponseResult(status="forbidden", invitation=invitation, inviter=inviter, invitee=user)
        if invitation.status != InvitationStatus.PENDING.value:
            return InvitationResponseResult(status="already_processed", invitation=invitation, inviter=inviter, invitee=user)
        if invitation.expires_at < datetime.utcnow():
            return InvitationResponseResult(status="expired", invitation=invitation, inviter=inviter, invitee=user)

        return InvitationResponseResult(status="ok", invitation=invitation, inviter=inviter, invitee=user)


def cancel_invitation(*, inviter_telegram_id: int, invitation_id: int) -> InvitationResponseResult:
    with session_scope() as session:
        inviter = session.execute(select(User).where(User.telegram_id == inviter_telegram_id)).scalar_one_or_none()
        if inviter is None:
            return InvitationResponseResult(status="inviter_missing")

        invitation = session.execute(select(Invitation).where(Invitation.id == invitation_id)).scalar_one_or_none()
        if invitation is None:
            return InvitationResponseResult(status="missing", inviter=inviter)
        if invitation.inviter_user_id != inviter.id:
            return InvitationResponseResult(status="forbidden", invitation=invitation, inviter=inviter)
        if invitation.status != InvitationStatus.PENDING.value:
            return InvitationResponseResult(status="already_processed", invitation=invitation, inviter=inviter)
        if invitation.expires_at < datetime.utcnow():
            invitation.status = InvitationStatus.EXPIRED.value
            session.flush()
            return InvitationResponseResult(status="expired", invitation=invitation, inviter=inviter)

        invitee = (
            session.execute(select(User).where(User.id == invitation.invitee_user_id)).scalar_one_or_none()
            if invitation.invitee_user_id
            else None
        )
        invitation.status = InvitationStatus.CANCELLED.value
        invitation.responded_at = datetime.utcnow()
        session.flush()
        return InvitationResponseResult(status="cancelled", invitation=invitation, inviter=inviter, invitee=invitee)


def claim_external_invitation(*, invitation_id: int, invitee_telegram_id: int) -> InvitationResponseResult:
    with session_scope() as session:
        invitee = session.execute(select(User).where(User.telegram_id == invitee_telegram_id)).scalar_one_or_none()
        if invitee is None:
            return InvitationResponseResult(status="invitee_missing")

        invitation = session.execute(select(Invitation).where(Invitation.id == invitation_id)).scalar_one_or_none()
        if invitation is None:
            return InvitationResponseResult(status="missing")

        inviter = session.execute(select(User).where(User.id == invitation.inviter_user_id)).scalar_one_or_none()
        if inviter is None:
            return InvitationResponseResult(status="inviter_missing", invitation=invitation, invitee=invitee)
        if invitation.expires_at < datetime.utcnow():
            invitation.status = InvitationStatus.EXPIRED.value
            session.flush()
            return InvitationResponseResult(status="expired", invitation=invitation, inviter=inviter, invitee=invitee)

        if invitation.invitee_user_id is None:
            if invitee.id == inviter.id:
                return InvitationResponseResult(status="self_invite", invitation=invitation, inviter=inviter, invitee=invitee)
            if invitation.status != InvitationStatus.PENDING.value:
                return InvitationResponseResult(status="already_processed", invitation=invitation, inviter=inviter, invitee=invitee)
            invitation.invitee_user_id = invitee.id
            invitation.invitee_external_text = None
            session.flush()
            return InvitationResponseResult(status="linked", invitation=invitation, inviter=inviter, invitee=invitee)

        if invitation.invitee_user_id == invitee.id:
            return InvitationResponseResult(status="already_linked", invitation=invitation, inviter=inviter, invitee=invitee)
        return InvitationResponseResult(status="forbidden", invitation=invitation, inviter=inviter, invitee=invitee)


def respond_to_invitation(*, invitee_telegram_id: int, invitation_id: int, accept: bool) -> InvitationResponseResult:
    with session_scope() as session:
        invitee = session.execute(select(User).where(User.telegram_id == invitee_telegram_id)).scalar_one_or_none()
        if invitee is None:
            return InvitationResponseResult(status="invitee_missing")

        invitation = session.execute(select(Invitation).where(Invitation.id == invitation_id)).scalar_one_or_none()
        if invitation is None:
            return InvitationResponseResult(status="missing")
        if invitation.invitee_user_id != invitee.id:
            return InvitationResponseResult(status="forbidden")
        if invitation.status != InvitationStatus.PENDING.value:
            return InvitationResponseResult(status="already_processed", invitation=invitation)
        if invitation.expires_at < datetime.utcnow():
            invitation.status = InvitationStatus.EXPIRED.value
            return InvitationResponseResult(status="expired", invitation=invitation)

        invitation.status = InvitationStatus.ACCEPTED.value if accept else InvitationStatus.DECLINED.value
        invitation.responded_at = datetime.utcnow()
        inviter = session.execute(select(User).where(User.id == invitation.inviter_user_id)).scalar_one_or_none()
        session.flush()

    match = create_match_from_invitation(invitation_id) if accept else None
    return InvitationResponseResult(
        status="accepted" if accept else "declined",
        invitation=invitation,
        inviter=inviter,
        invitee=invitee,
        match=match,
    )


def expire_pending_invitations() -> list[ExpiredInvitationRecord]:
    now = datetime.utcnow()
    with session_scope() as session:
        invitations = session.execute(
            select(Invitation).where(Invitation.status == InvitationStatus.PENDING.value, Invitation.expires_at < now)
        ).scalars().all()
        expired = []
        for invitation in invitations:
            invitation.status = InvitationStatus.EXPIRED.value
            inviter = session.execute(select(User).where(User.id == invitation.inviter_user_id)).scalar_one()
            invitee = (
                session.execute(select(User).where(User.id == invitation.invitee_user_id)).scalar_one_or_none()
                if invitation.invitee_user_id
                else None
            )
            expired.append(ExpiredInvitationRecord(invitation=invitation, inviter=inviter, invitee=invitee))
        session.flush()
        return expired
