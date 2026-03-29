from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from bot.config import get_settings
from bot.db import session_scope
from bot.models import Club, Rating, User, UserWeapon


CITY_ALIASES = {
    "moscow": "Москва",
    "москва": "Москва",
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

CLUB_ALIASES = {
    "mws": "Men With Swords",
    "men with swords": "Men With Swords",
    "counter time": "CounterTime",
    "countertime": "CounterTime",
    "контрвремя": "CounterTime",
    "paladin": "FFC Paladin",
    "паладин": "FFC Paladin",
    "paladin ffc": "FFC Paladin",
    "ffc paladin": "FFC Paladin",
    "ffc paladin, fencing fanatics": "FFC Paladin",
}


def _normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _is_broken_text(value: str) -> bool:
    normalized = _normalize_spaces(value)
    if not normalized:
        return True
    if "?" in normalized or "�" in normalized:
        return True
    letters = [char for char in normalized if char.isalpha()]
    return bool(letters) and all(char == letters[0] for char in letters) and letters[0] in {"?", "�"}


def normalize_city_name(city: str | None) -> str:
    raw = _normalize_spaces(city or "")
    if not raw or raw == "-" or _is_broken_text(raw):
        return "Не указан"
    normalized_key = raw.replace("-", " ").casefold()
    return CITY_ALIASES.get(normalized_key, raw)


def normalize_club_name(club_name: str | None) -> str | None:
    raw = _normalize_spaces(club_name or "")
    if not raw or raw == "-" or _is_broken_text(raw):
        return None
    normalized_key = raw.replace("-", " ").casefold()
    return CLUB_ALIASES.get(normalized_key, raw)


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
        clubs = {
            normalized
            for item in session.execute(select(Club.name)).scalars().all()
            if (normalized := normalize_club_name(item))
        }
        clubs.update(
            normalized
            for item in session.execute(select(User.custom_club_name)).scalars().all()
            if (normalized := normalize_club_name(item))
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
        normalized_club_name = normalize_club_name(club_name)
        if normalized_club_name:
            club = next(
                (
                    item
                    for item in session.execute(select(Club)).scalars().all()
                    if normalize_club_name(item.name) == normalized_club_name
                ),
                None,
            )
            if club is None:
                custom_club_name = normalized_club_name

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
