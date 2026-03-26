from __future__ import annotations

import json
from pathlib import Path

from bot.config import get_settings
from bot.db import engine, session_scope
from bot.enums import ClubKind
from bot.models import Base, Club, Rating, User, UserWeapon


ROOT = Path(__file__).resolve().parent.parent
SEEDS_DIR = ROOT / "seeds"


def load_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def seed_clubs() -> None:
    clubs_data = load_json(SEEDS_DIR / "clubs.seed.json")
    with session_scope() as session:
        for item in clubs_data:
            club = session.query(Club).filter_by(name=item["name"]).one_or_none()
            if club is None:
                club = Club(name=item["name"])
                session.add(club)
            club.city = item["city"]
            club.kind = item.get("kind", ClubKind.FENCING.value)
            club.source_url = item.get("source_url")
            club.is_active = True


def seed_users() -> None:
    settings = get_settings()
    users_data = load_json(SEEDS_DIR / "users.seed.json")
    with session_scope() as session:
        for item in users_data:
            user = session.query(User).filter_by(telegram_id=item["telegram_id"]).one_or_none()
            club = session.query(Club).filter_by(name=item.get("club_name")).one_or_none()
            if user is None:
                user = User(telegram_id=item["telegram_id"])
                session.add(user)
                session.flush()

            user.username = item.get("username")
            user.display_name = item.get("display_name")
            user.full_name = item["full_name"]
            user.city = item["city"]
            user.club_id = club.id if club else None
            user.custom_club_name = None if club else item.get("club_name")
            user.is_admin = item.get("is_admin", False)
            user.is_active = True
            session.flush()

            existing_weapons = {weapon.weapon_type: weapon for weapon in session.query(UserWeapon).filter_by(user_id=user.id).all()}
            existing_ratings = {rating.weapon_type: rating for rating in session.query(Rating).filter_by(user_id=user.id).all()}
            desired_weapons = {weapon["weapon_type"]: weapon for weapon in item.get("weapons", [])}

            for weapon_type, payload in desired_weapons.items():
                weapon = existing_weapons.get(weapon_type)
                if weapon is None:
                    weapon = UserWeapon(user_id=user.id, weapon_type=weapon_type)
                    session.add(weapon)
                weapon.readiness_status = payload["readiness_status"]

                rating = existing_ratings.get(weapon_type)
                if rating is None:
                    rating = Rating(user_id=user.id, weapon_type=weapon_type)
                    session.add(rating)
                rating.rating_value = payload.get("rating", settings.default_elo_rating)

            for weapon_type, weapon in existing_weapons.items():
                if weapon_type not in desired_weapons:
                    session.delete(weapon)
            for weapon_type, rating in existing_ratings.items():
                if weapon_type not in desired_weapons:
                    session.delete(rating)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    seed_clubs()
    seed_users()
    print("Database initialized and seeds loaded.")


if __name__ == "__main__":
    main()
