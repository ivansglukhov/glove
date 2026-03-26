from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_telegram_id: int
    database_url: str = "sqlite:///glove.sqlite3"
    default_elo_rating: int = 1000
    elo_k_factor: int = 32
    invitation_ttl_days: int = 7
    match_confirm_ttl_days: int = 7


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    bot_token = os.getenv("BOT_TOKEN", "")
    admin_telegram_id = int(os.getenv("ADMIN_TELEGRAM_ID", "0"))
    return Settings(
        bot_token=bot_token,
        admin_telegram_id=admin_telegram_id,
        database_url=os.getenv("DATABASE_URL", "sqlite:///glove.sqlite3"),
        default_elo_rating=int(os.getenv("DEFAULT_ELO_RATING", "1000")),
        elo_k_factor=int(os.getenv("ELO_K_FACTOR", "32")),
        invitation_ttl_days=int(os.getenv("INVITATION_TTL_DAYS", "7")),
        match_confirm_ttl_days=int(os.getenv("MATCH_CONFIRM_TTL_DAYS", "7")),
    )
