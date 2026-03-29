from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db import session_scope
from bot.models import Club, Rating, User, UserWeapon


CITY_ALIASES = {
    "спб": "Санкт-Петербург",
    "санкт петербург": "Санкт-Петербург",
    "санкт-петербург": "Санкт-Петербург",
    "санкт петербуг": "Санкт-Петербург",
    "санкт-петербуг": "Санкт-Петербург",
    "питер": "Санкт-Петербург",
    "saint petersburg": "Санкт-Петербург",
    "st petersburg": "Санкт-Петербург",
    "st. petersburg": "Санкт-Петербург",
    "sankt petersburg": "Санкт-Петербург",
    "sankt-petersburg": "Санкт-Петербург",
}


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_city_name(city: str | None) -> str:
    raw = _normalize_spaces(city or "")
    if not raw or raw == "-":
        return "Не указан"
    normalized_key = raw.replace("-", " ").casefold()
    return CITY_ALIASES.get(normalized_key, raw)


def list_known_city_names() -> list[str]:
    with session_scope() as session:
        cities = {
            normalize_city_name(item)
            for item in session.execute(select(User.city)).scalars().all()
            if item and normalize_city_name(item) != "Не указан"
        }
        cities.update(
            normalize_city_name(item)
            for item in session.execute(select(Club.city)).scalars().all()
            if item and normalize_city_name(item) != "Не указан"
        )
        return sorted(cities, key=str.casefold)


def list_known_club_names() -> list[str]:
    with session_scope() as session:
        clubs = {item for item in session.execute(select(Club.name)).scalars().all() if item}
        clubs.update(
            item.strip()
            for item in session.execute(select(User.custom_club_name)).scalars().all()
            if item and item.strip() and item.strip() != "-"
        )
        return sorted(clubs, key=str.casefold)


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
                city=normalize_city_name(city),
                club_id=club.id if club else None,
                custom_club_name=custom_club_name,
            )
            session.add(user)
            session.flush()
        else:
            user.username = username
            user.display_name = display_name
            user.full_name = full_name.strip()
            user.city = normalize_city_name(city)
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
