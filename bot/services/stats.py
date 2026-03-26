from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select

from bot.db import session_scope
from bot.enums import MatchStatus
from bot.models import Match, Rating, User


@dataclass(slots=True)
class RecentMatch:
    match_id: int
    weapon_type: str
    result: str
    opponent_name: str
    completed_at: object


@dataclass(slots=True)
class StatsSummary:
    registered_at: object
    total: int
    wins: int
    losses: int
    draws: int
    win_rate: int
    ratings: list[tuple[str, int]]
    recent: list[RecentMatch]


def get_user_stats(telegram_id: int) -> StatsSummary | None:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user is None:
            return None

        matches = session.execute(
            select(Match).where(
                Match.status.in_([MatchStatus.COMPLETED.value, MatchStatus.AUTO_DRAW.value]),
                or_(Match.fighter_a_id == user.id, Match.fighter_b_id == user.id),
            ).order_by(Match.completed_at.desc())
        ).scalars().all()

        wins = losses = draws = 0
        recent = []
        for match in matches:
            opponent_id = match.fighter_b_id if match.fighter_a_id == user.id else match.fighter_a_id
            opponent = session.execute(select(User).where(User.id == opponent_id)).scalar_one()
            if match.proposed_is_draw:
                result = 'Ничья'
                draws += 1
            elif match.proposed_winner_user_id == user.id:
                result = 'Победа'
                wins += 1
            else:
                result = 'Поражение'
                losses += 1
            if len(recent) < 5:
                recent.append(
                    RecentMatch(
                        match_id=match.id,
                        weapon_type=match.weapon_type,
                        result=result,
                        opponent_name=opponent.display_name or opponent.full_name,
                        completed_at=match.completed_at,
                    )
                )

        total = len(matches)
        ratings = session.execute(select(Rating).where(Rating.user_id == user.id).order_by(Rating.weapon_type.asc())).scalars().all()
        win_rate = round((wins / total) * 100) if total else 0
        return StatsSummary(
            registered_at=user.registered_at,
            total=total,
            wins=wins,
            losses=losses,
            draws=draws,
            win_rate=win_rate,
            ratings=[(item.weapon_type, item.rating_value) for item in ratings],
            recent=recent,
        )
