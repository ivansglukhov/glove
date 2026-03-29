from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from bot.db import session_scope
from bot.models import Complaint, Suggestion, User


@dataclass(slots=True)
class ComplaintView:
    complaint_id: int
    from_name: str
    from_telegram_id: int
    match_id: int | None
    text: str
    status: str


@dataclass(slots=True)
class SuggestionView:
    suggestion_id: int
    from_name: str
    from_telegram_id: int
    text: str


@dataclass(slots=True)
class FeedbackItemView:
    kind: str
    item_id: int
    from_name: str
    from_telegram_id: int
    text: str
    match_id: int | None
    status: str | None
    created_at: object


def create_complaint(*, from_telegram_id: int, text: str, match_id: int | None = None) -> Complaint | None:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == from_telegram_id)).scalar_one_or_none()
        if user is None:
            return None
        complaint = Complaint(from_user_id=user.id, match_id=match_id, text=text.strip())
        session.add(complaint)
        session.flush()
        session.refresh(complaint)
        return complaint


def create_suggestion(*, from_telegram_id: int, text: str) -> Suggestion | None:
    with session_scope() as session:
        user = session.execute(select(User).where(User.telegram_id == from_telegram_id)).scalar_one_or_none()
        if user is None:
            return None
        suggestion = Suggestion(from_user_id=user.id, text=text.strip())
        session.add(suggestion)
        session.flush()
        session.refresh(suggestion)
        return suggestion


def list_complaints(status: str | None = None) -> list[ComplaintView]:
    with session_scope() as session:
        stmt = select(Complaint).order_by(Complaint.created_at.desc())
        if status:
            stmt = stmt.where(Complaint.status == status)
        items = session.execute(stmt).scalars().all()
        result = []
        for item in items:
            user = session.execute(select(User).where(User.id == item.from_user_id)).scalar_one()
            result.append(
                ComplaintView(
                    complaint_id=item.id,
                    from_name=user.display_name or user.full_name,
                    from_telegram_id=user.telegram_id,
                    match_id=item.match_id,
                    text=item.text,
                    status=item.status,
                )
            )
        return result


def list_suggestions() -> list[SuggestionView]:
    with session_scope() as session:
        items = session.execute(select(Suggestion).order_by(Suggestion.created_at.desc())).scalars().all()
        result = []
        for item in items:
            user = session.execute(select(User).where(User.id == item.from_user_id)).scalar_one()
            result.append(
                SuggestionView(
                    suggestion_id=item.id,
                    from_name=user.display_name or user.full_name,
                    from_telegram_id=user.telegram_id,
                    text=item.text,
                )
            )
        return result


def list_feedback_items(limit: int = 20) -> list[FeedbackItemView]:
    with session_scope() as session:
        items: list[FeedbackItemView] = []

        for item in session.execute(select(Complaint).order_by(Complaint.created_at.desc())).scalars().all():
            user = session.execute(select(User).where(User.id == item.from_user_id)).scalar_one()
            items.append(
                FeedbackItemView(
                    kind="complaint",
                    item_id=item.id,
                    from_name=user.full_name,
                    from_telegram_id=user.telegram_id,
                    text=item.text,
                    match_id=item.match_id,
                    status=item.status,
                    created_at=item.created_at,
                )
            )

        for item in session.execute(select(Suggestion).order_by(Suggestion.created_at.desc())).scalars().all():
            user = session.execute(select(User).where(User.id == item.from_user_id)).scalar_one()
            items.append(
                FeedbackItemView(
                    kind="suggestion",
                    item_id=item.id,
                    from_name=user.full_name,
                    from_telegram_id=user.telegram_id,
                    text=item.text,
                    match_id=None,
                    status=None,
                    created_at=item.created_at,
                )
            )

        items.sort(key=lambda item: item.created_at, reverse=True)
        return items[:limit]


def delete_feedback_item(*, kind: str, item_id: int) -> bool:
    with session_scope() as session:
        if kind == "complaint":
            item = session.execute(select(Complaint).where(Complaint.id == item_id)).scalar_one_or_none()
        elif kind == "suggestion":
            item = session.execute(select(Suggestion).where(Suggestion.id == item_id)).scalar_one_or_none()
        else:
            return False
        if item is None:
            return False
        session.delete(item)
        session.flush()
        return True


def mark_complaint_resolved(complaint_id: int) -> bool:
    with session_scope() as session:
        complaint = session.execute(select(Complaint).where(Complaint.id == complaint_id)).scalar_one_or_none()
        if complaint is None:
            return False
        complaint.status = 'resolved'
        session.flush()
        return True
