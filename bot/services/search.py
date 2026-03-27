from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from bot.db import session_scope
from bot.enums import MatchStatus, ReadinessStatus
from bot.models import Match, User, UserWeapon


ACTIVE_SEARCH_STATUSES = {
    ReadinessStatus.READY.value,
    ReadinessStatus.READY_TODAY.value,
    ReadinessStatus.READY_SOON.value,
    ReadinessStatus.ACTIVELY_LOOKING.value,
}


@dataclass(slots=True)
class SearchCard:
    telegram_id: int
    display_name: str | None
    full_name: str
    club_name: str
    city: str
    weapon_type: str
    readiness_status: str
    rating: int
    win_rate: int
    username: str | None


@dataclass(slots=True)
class SearchResult:
    user: User
    card: SearchCard


def _club_name(user: User) -> str:
    return user.club.name if user.club else (user.custom_club_name or "Без клуба")


def _rating_for_weapon(user: User, weapon_type: str) -> int:
    for rating in user.ratings:
        if rating.weapon_type == weapon_type:
            return rating.rating_value
    return 1000


def _status_for_weapon(user: User, weapon_type: str) -> str | None:
    for weapon in user.weapons:
        if weapon.weapon_type == weapon_type:
            return weapon.readiness_status
    return None


def _win_rate(session, user_id: int, weapon_type: str) -> int:
    total_stmt = select(func.count(Match.id)).where(
        Match.weapon_type == weapon_type,
        Match.status.in_([MatchStatus.COMPLETED.value, MatchStatus.AUTO_DRAW.value]),
        or_(Match.fighter_a_id == user_id, Match.fighter_b_id == user_id),
    )
    wins_stmt = select(func.count(Match.id)).where(
        Match.weapon_type == weapon_type,
        Match.status == MatchStatus.COMPLETED.value,
        Match.proposed_is_draw.is_(False),
        Match.proposed_winner_user_id == user_id,
    )
    total = session.execute(total_stmt).scalar_one()
    if not total:
        return 0
    wins = session.execute(wins_stmt).scalar_one()
    return round((wins / total) * 100)


def _to_result(session, user: User, weapon_type: str) -> SearchResult:
    card = SearchCard(
        telegram_id=user.telegram_id,
        display_name=user.display_name,
        full_name=user.full_name,
        club_name=_club_name(user),
        city=user.city,
        weapon_type=weapon_type,
        readiness_status=_status_for_weapon(user, weapon_type) or ReadinessStatus.NOT_READY.value,
        rating=_rating_for_weapon(user, weapon_type),
        win_rate=_win_rate(session, user.id, weapon_type),
        username=user.username,
    )
    return SearchResult(user=user, card=card)


def search_by_filters(*, requester_telegram_id: int, weapon_type: str, own_club_only: bool = False, club_name: str | None = None) -> list[SearchResult]:
    with session_scope() as session:
        requester_stmt = (
            select(User)
            .where(User.telegram_id == requester_telegram_id)
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )
        requester = session.execute(requester_stmt).scalar_one_or_none()
        if requester is None:
            return []

        stmt = (
            select(User)
            .join(UserWeapon, UserWeapon.user_id == User.id)
            .where(
                User.is_active.is_(True),
                User.telegram_id != requester_telegram_id,
                User.city == requester.city,
                UserWeapon.weapon_type == weapon_type,
                UserWeapon.readiness_status.in_(list(ACTIVE_SEARCH_STATUSES)),
            )
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )

        users = session.execute(stmt).scalars().unique().all()

        if own_club_only:
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
        return [_to_result(session, user, weapon_type) for user in users]


def search_by_telegram_id(*, telegram_id: int, weapon_type: str) -> list[SearchResult]:
    with session_scope() as session:
        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id, User.is_active.is_(True))
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )
        user = session.execute(stmt).scalar_one_or_none()
        if user is None:
            return []
        return [_to_result(session, user, weapon_type)]


def search_by_username(*, username: str, weapon_type: str) -> list[SearchResult]:
    normalized = username.lstrip("@").strip()
    with session_scope() as session:
        stmt = (
            select(User)
            .where(func.lower(User.username) == normalized.lower(), User.is_active.is_(True))
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )
        users = session.execute(stmt).scalars().unique().all()
        return [_to_result(session, user, weapon_type) for user in users]


def search_by_full_name(*, full_name_query: str, weapon_type: str) -> list[SearchResult]:
    normalized_query = full_name_query.strip().lower()
    if not normalized_query:
        return []
    with session_scope() as session:
        stmt = (
            select(User)
            .where(User.is_active.is_(True))
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
            .order_by(User.full_name.asc())
        )
        users = [
            user for user in session.execute(stmt).scalars().unique().all()
            if normalized_query in user.full_name.lower()
        ]
        return [_to_result(session, user, weapon_type) for user in users]
