from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import or_, select

from bot.config import get_settings
from bot.db import session_scope
from bot.enums import MatchStatus
from bot.models import Invitation, Match, MatchNote, Rating, RatingHistory, User
from bot.services.elo import calculate_elo_delta


@dataclass(slots=True)
class MatchView:
    match_id: int
    status: str
    weapon_type: str
    created_at: datetime
    other_name: str
    proposed_by_name: str | None
    proposed_winner_name: str | None
    proposed_is_draw: bool
    completed_at: datetime | None
    my_note: str | None


@dataclass(slots=True)
class MatchResultAction:
    status: str
    match: Match | None = None
    actor: User | None = None
    other: User | None = None
    winner: User | None = None
    actor_note: str | None = None


@dataclass(slots=True)
class AutoDrawRecord:
    match: Match
    fighter_a: User
    fighter_b: User


def _display_name(user: User) -> str:
    return user.full_name


def create_match_from_invitation(invitation_id: int) -> Match | None:
    settings = get_settings()
    with session_scope() as session:
        invitation = session.execute(select(Invitation).where(Invitation.id == invitation_id)).scalar_one_or_none()
        if invitation is None or invitation.invitee_user_id is None:
            return None

        existing = session.execute(select(Match).where(Match.invitation_id == invitation_id)).scalar_one_or_none()
        if existing is not None:
            return existing

        match = Match(
            invitation_id=invitation.id,
            fighter_a_id=invitation.inviter_user_id,
            fighter_b_id=invitation.invitee_user_id,
            weapon_type=invitation.weapon_type,
            status=MatchStatus.ACTIVE.value,
            confirmation_deadline_at=datetime.utcnow() + timedelta(days=settings.match_confirm_ttl_days),
        )
        session.add(match)
        session.flush()
        session.refresh(match)
        return match


def list_matches(telegram_id: int) -> list[MatchView]:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == telegram_id)).scalar_one_or_none()
        if user is None:
            return []

        matches = session.execute(
            select(Match)
            .where(or_(Match.fighter_a_id == user.id, Match.fighter_b_id == user.id))
            .order_by(Match.created_at.desc())
        ).scalars().all()

        result = []
        for item in matches:
            other_id = item.fighter_b_id if item.fighter_a_id == user.id else item.fighter_a_id
            other = session.execute(select(User).where(User.id == other_id)).scalar_one()
            proposer = None
            winner = None
            if item.result_proposed_by_user_id:
                proposer = session.execute(select(User).where(User.id == item.result_proposed_by_user_id)).scalar_one_or_none()
            if item.proposed_winner_user_id:
                winner = session.execute(select(User).where(User.id == item.proposed_winner_user_id)).scalar_one_or_none()
            note = session.execute(
                select(MatchNote).where(MatchNote.match_id == item.id, MatchNote.author_user_id == user.id)
            ).scalar_one_or_none()
            result.append(
                MatchView(
                    match_id=item.id,
                    status=item.status,
                    weapon_type=item.weapon_type,
                    created_at=item.created_at,
                    other_name=_display_name(other),
                    proposed_by_name=_display_name(proposer) if proposer else None,
                    proposed_winner_name=_display_name(winner) if winner else None,
                    proposed_is_draw=item.proposed_is_draw,
                    completed_at=item.completed_at,
                    my_note=note.note_text if note else None,
                )
            )
        return result


def propose_match_result(*, actor_telegram_id: int, match_id: int, outcome: str, note_text: str | None) -> MatchResultAction:
    settings = get_settings()
    with session_scope() as session:
        actor = session.execute(select(User).where(User.telegram_id == actor_telegram_id)).scalar_one_or_none()
        if actor is None:
            return MatchResultAction(status="actor_missing")
        match = session.execute(select(Match).where(Match.id == match_id)).scalar_one_or_none()
        if match is None:
            return MatchResultAction(status="missing")
        if actor.id not in {match.fighter_a_id, match.fighter_b_id}:
            return MatchResultAction(status="forbidden")
        if match.status in {MatchStatus.COMPLETED.value, MatchStatus.AUTO_DRAW.value}:
            return MatchResultAction(status="already_completed", match=match)

        other_id = match.fighter_b_id if actor.id == match.fighter_a_id else match.fighter_a_id
        other = session.execute(select(User).where(User.id == other_id)).scalar_one()

        winner = None
        is_draw = False
        if outcome == "self":
            winner = actor
        elif outcome == "other":
            winner = other
        else:
            is_draw = True

        match.result_proposed_by_user_id = actor.id
        match.proposed_winner_user_id = winner.id if winner else None
        match.proposed_is_draw = is_draw
        match.status = MatchStatus.AWAITING_CONFIRMATION.value
        match.confirmation_deadline_at = datetime.utcnow() + timedelta(days=settings.match_confirm_ttl_days)

        existing_note = session.execute(
            select(MatchNote).where(MatchNote.match_id == match.id, MatchNote.author_user_id == actor.id)
        ).scalar_one_or_none()
        if note_text:
            if existing_note is None:
                session.add(MatchNote(match_id=match.id, author_user_id=actor.id, note_text=note_text.strip()))
            else:
                existing_note.note_text = note_text.strip()

        session.flush()
        return MatchResultAction(
            status="proposed",
            match=match,
            actor=actor,
            other=other,
            winner=winner,
            actor_note=note_text.strip() if note_text else None,
        )


def _get_rating(session, user_id: int, weapon_type: str) -> Rating:
    rating = session.execute(select(Rating).where(Rating.user_id == user_id, Rating.weapon_type == weapon_type)).scalar_one_or_none()
    if rating is None:
        rating = Rating(user_id=user_id, weapon_type=weapon_type, rating_value=get_settings().default_elo_rating)
        session.add(rating)
        session.flush()
    return rating


def _apply_rating_changes(session, match: Match) -> None:
    settings = get_settings()
    a_rating = _get_rating(session, match.fighter_a_id, match.weapon_type)
    b_rating = _get_rating(session, match.fighter_b_id, match.weapon_type)

    if match.proposed_is_draw:
        a_score = 0.5
        b_score = 0.5
    elif match.proposed_winner_user_id == match.fighter_a_id:
        a_score = 1.0
        b_score = 0.0
    else:
        a_score = 0.0
        b_score = 1.0

    a_delta = calculate_elo_delta(a_rating.rating_value, b_rating.rating_value, a_score, settings.elo_k_factor)
    b_delta = calculate_elo_delta(b_rating.rating_value, a_rating.rating_value, b_score, settings.elo_k_factor)

    old_a = a_rating.rating_value
    old_b = b_rating.rating_value
    a_rating.rating_value += a_delta
    b_rating.rating_value += b_delta
    a_rating.updated_at = datetime.utcnow()
    b_rating.updated_at = datetime.utcnow()

    session.add(RatingHistory(user_id=match.fighter_a_id, match_id=match.id, weapon_type=match.weapon_type, old_rating=old_a, new_rating=a_rating.rating_value, delta=a_delta))
    session.add(RatingHistory(user_id=match.fighter_b_id, match_id=match.id, weapon_type=match.weapon_type, old_rating=old_b, new_rating=b_rating.rating_value, delta=b_delta))


def confirm_match_result(*, actor_telegram_id: int, match_id: int, agree: bool) -> MatchResultAction:
    with session_scope() as session:
        actor = session.execute(select(User).where(User.telegram_id == actor_telegram_id)).scalar_one_or_none()
        if actor is None:
            return MatchResultAction(status="actor_missing")
        match = session.execute(select(Match).where(Match.id == match_id)).scalar_one_or_none()
        if match is None:
            return MatchResultAction(status="missing")
        if actor.id not in {match.fighter_a_id, match.fighter_b_id}:
            return MatchResultAction(status="forbidden")
        if match.status in {MatchStatus.COMPLETED.value, MatchStatus.AUTO_DRAW.value}:
            return MatchResultAction(status="already_completed", match=match)
        if match.result_proposed_by_user_id is None:
            return MatchResultAction(status="no_result", match=match)
        if match.result_proposed_by_user_id == actor.id:
            return MatchResultAction(status="own_proposal", match=match)

        other_id = match.fighter_b_id if actor.id == match.fighter_a_id else match.fighter_a_id
        other = session.execute(select(User).where(User.id == other_id)).scalar_one()
        winner = None
        if match.proposed_winner_user_id:
            winner = session.execute(select(User).where(User.id == match.proposed_winner_user_id)).scalar_one_or_none()

        if agree:
            match.status = MatchStatus.COMPLETED.value
            match.completed_at = datetime.utcnow()
            _apply_rating_changes(session, match)
            session.flush()
            return MatchResultAction(status="confirmed", match=match, actor=actor, other=other, winner=winner)

        match.status = MatchStatus.DISPUTED.value
        session.flush()
        return MatchResultAction(status="disputed", match=match, actor=actor, other=other, winner=winner)


def auto_draw_overdue_matches() -> list[AutoDrawRecord]:
    now = datetime.utcnow()
    with session_scope() as session:
        matches = session.execute(
            select(Match).where(
                Match.status.in_([MatchStatus.AWAITING_CONFIRMATION.value, MatchStatus.DISPUTED.value]),
                Match.confirmation_deadline_at < now,
            )
        ).scalars().all()
        result = []
        for match in matches:
            match.status = MatchStatus.AUTO_DRAW.value
            match.proposed_is_draw = True
            match.proposed_winner_user_id = None
            match.completed_at = now
            _apply_rating_changes(session, match)
            fighter_a = session.execute(select(User).where(User.id == match.fighter_a_id)).scalar_one()
            fighter_b = session.execute(select(User).where(User.id == match.fighter_b_id)).scalar_one()
            result.append(AutoDrawRecord(match=match, fighter_a=fighter_a, fighter_b=fighter_b))
        session.flush()
        return result


def admin_resolve_match(*, match_id: int, outcome: str) -> MatchResultAction:
    with session_scope() as session:
        match = session.execute(select(Match).where(Match.id == match_id)).scalar_one_or_none()
        if match is None:
            return MatchResultAction(status="missing")
        fighter_a = session.execute(select(User).where(User.id == match.fighter_a_id)).scalar_one()
        fighter_b = session.execute(select(User).where(User.id == match.fighter_b_id)).scalar_one()

        if outcome == "a":
            match.proposed_winner_user_id = fighter_a.id
            match.proposed_is_draw = False
            winner = fighter_a
        elif outcome == "b":
            match.proposed_winner_user_id = fighter_b.id
            match.proposed_is_draw = False
            winner = fighter_b
        else:
            match.proposed_winner_user_id = None
            match.proposed_is_draw = True
            winner = None

        match.status = MatchStatus.COMPLETED.value
        match.completed_at = datetime.utcnow()
        _apply_rating_changes(session, match)
        session.flush()
        return MatchResultAction(status="resolved", match=match, actor=fighter_a, other=fighter_b, winner=winner)
