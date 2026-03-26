from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db import session_scope
from bot.models import Club, Rating, User, UserWeapon


def get_user_by_telegram_id(telegram_id: int) -> User | None:
    with session_scope() as session:
        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )
        return session.execute(stmt).scalar_one_or_none()


def upsert_user_profile(
    *,
    telegram_id: int,
    username: str | None,
    display_name: str | None,
    full_name: str,
    city: str,
    club_name: str | None,
    weapons: list[dict[str, str]],
) -> User:
    settings = get_settings()
    with session_scope() as session:
        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.weapons), selectinload(User.ratings), selectinload(User.club))
        )
        user = session.execute(stmt).scalar_one_or_none()

        club = None
        custom_club_name = None
        if club_name:
            club = session.execute(select(Club).where(Club.name.ilike(club_name.strip()))).scalar_one_or_none()
            if club is None:
                custom_club_name = club_name.strip()

        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                display_name=display_name,
                full_name=full_name.strip(),
                city=city.strip(),
                club_id=club.id if club else None,
                custom_club_name=custom_club_name,
            )
            session.add(user)
            session.flush()
        else:
            user.username = username
            user.display_name = display_name
            user.full_name = full_name.strip()
            user.city = city.strip()
            user.club_id = club.id if club else None
            user.custom_club_name = custom_club_name
            for weapon in list(user.weapons):
                session.delete(weapon)
            for rating in list(user.ratings):
                session.delete(rating)
            session.flush()

        for item in weapons:
            session.add(
                UserWeapon(
                    user_id=user.id,
                    weapon_type=item["weapon_type"],
                    readiness_status=item["readiness_status"],
                )
            )
            session.add(
                Rating(
                    user_id=user.id,
                    weapon_type=item["weapon_type"],
                    rating_value=settings.default_elo_rating,
                )
            )

        session.flush()
        session.refresh(user)
        user = session.execute(stmt).scalar_one()
        return user


def update_user_weapon_statuses(telegram_id: int, statuses: list[dict[str, str]]) -> User | None:
    with session_scope() as session:
        stmt = (
            select(User)
            .where(User.telegram_id == telegram_id)
            .options(selectinload(User.club), selectinload(User.weapons), selectinload(User.ratings))
        )
        user = session.execute(stmt).scalar_one_or_none()
        if user is None:
            return None

        by_weapon = {weapon.weapon_type: weapon for weapon in user.weapons}
        for item in statuses:
            weapon = by_weapon.get(item["weapon_type"])
            if weapon is not None:
                weapon.readiness_status = item["readiness_status"]

        session.flush()
        user = session.execute(stmt).scalar_one()
        return user
