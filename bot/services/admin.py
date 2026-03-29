from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, or_, select

from bot.db import session_scope
from bot.enums import MatchStatus
from bot.models import Complaint, Invitation, MailMessage, Match, MatchNote, Rating, RatingHistory, Suggestion, User, UserWeapon


@dataclass(slots=True)
class AdminUserView:
    telegram_id: int
    name: str
    city: str
    club: str
    registered_at: object


@dataclass(slots=True)
class AdminMatchView:
    match_id: int
    status: str
    weapon_type: str
    fighter_a: str
    fighter_b: str
    created_at: object


@dataclass(slots=True)
class AdminEventSummary:
    users: int
    complaints_new: int
    suggestions: int
    disputed_matches: int
    pending_invitations: int


def list_users(limit: int | None = None) -> list[AdminUserView]:
    with session_scope() as session:
        stmt = select(User).where(User.is_active.is_(True)).order_by(User.registered_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        items = session.execute(stmt).scalars().all()
        return [
            AdminUserView(
                telegram_id=item.telegram_id,
                name=item.full_name,
                city=item.city,
                club=item.club.name if item.club else (item.custom_club_name or 'Не указан'),
                registered_at=item.registered_at,
            )
            for item in items
        ]


def list_matches(limit: int | None = None, disputed_only: bool = False) -> list[AdminMatchView]:
    with session_scope() as session:
        stmt = select(Match).order_by(Match.created_at.asc())
        if disputed_only:
            stmt = select(Match).where(Match.status == MatchStatus.DISPUTED.value).order_by(Match.created_at.asc())
        if limit is not None:
            stmt = stmt.limit(limit)
        items = session.execute(stmt).scalars().all()
        result = []
        for item in items:
            fighter_a = session.execute(select(User).where(User.id == item.fighter_a_id)).scalar_one()
            fighter_b = session.execute(select(User).where(User.id == item.fighter_b_id)).scalar_one()
            result.append(
                AdminMatchView(
                    match_id=item.id,
                    status=item.status,
                    weapon_type=item.weapon_type,
                    fighter_a=fighter_a.full_name,
                    fighter_b=fighter_b.full_name,
                    created_at=item.created_at,
                )
            )
        return result


def get_event_summary() -> AdminEventSummary:
    with session_scope() as session:
        return AdminEventSummary(
            users=session.query(User).count(),
            complaints_new=session.query(Complaint).filter(Complaint.status == 'new').count(),
            suggestions=session.query(Suggestion).count(),
            disputed_matches=session.query(Match).filter(Match.status == MatchStatus.DISPUTED.value).count(),
            pending_invitations=session.query(Invitation).filter(Invitation.status == 'pending').count(),
        )


def delete_user_data(telegram_id: int) -> bool:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user is None or user.is_admin:
            return False

        match_ids = session.execute(
            select(Match.id).where(
                or_(
                    Match.fighter_a_id == user.id,
                    Match.fighter_b_id == user.id,
                    Match.result_proposed_by_user_id == user.id,
                    Match.proposed_winner_user_id == user.id,
                )
            )
        ).scalars().all()

        if match_ids:
            session.execute(delete(Complaint).where(Complaint.match_id.in_(match_ids)))
            session.execute(delete(RatingHistory).where(RatingHistory.match_id.in_(match_ids)))
            session.execute(delete(MatchNote).where(MatchNote.match_id.in_(match_ids)))
            session.execute(delete(Match).where(Match.id.in_(match_ids)))

        session.execute(
            delete(Complaint).where(
                or_(
                    Complaint.from_user_id == user.id,
                    Complaint.target_user_id == user.id,
                )
            )
        )
        session.execute(delete(Suggestion).where(Suggestion.from_user_id == user.id))
        session.execute(
            delete(Invitation).where(
                or_(
                    Invitation.inviter_user_id == user.id,
                    Invitation.invitee_user_id == user.id,
                )
            )
        )
        session.execute(
            delete(MailMessage).where(
                or_(
                    MailMessage.from_user_id == user.id,
                    MailMessage.to_user_id == user.id,
                )
            )
        )
        session.execute(delete(RatingHistory).where(RatingHistory.user_id == user.id))
        session.execute(delete(MatchNote).where(MatchNote.author_user_id == user.id))
        session.execute(delete(UserWeapon).where(UserWeapon.user_id == user.id))
        session.execute(delete(Rating).where(Rating.user_id == user.id))
        session.delete(user)
        session.flush()
        return True
