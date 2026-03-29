from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bot.db import session_scope
from bot.enums import MatchStatus
from bot.models import Complaint, Invitation, Match, Suggestion, User


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


def list_users(limit: int = 10) -> list[AdminUserView]:
    with session_scope() as session:
        items = session.execute(select(User).order_by(User.registered_at.desc()).limit(limit)).scalars().all()
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


def list_matches(limit: int = 10, disputed_only: bool = False) -> list[AdminMatchView]:
    with session_scope() as session:
        stmt = select(Match).order_by(Match.created_at.desc()).limit(limit)
        if disputed_only:
            stmt = select(Match).where(Match.status == MatchStatus.DISPUTED.value).order_by(Match.created_at.desc()).limit(limit)
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
