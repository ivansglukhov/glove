from __future__ import annotations

from telegram.ext import Application

from bot.services.invitations import expire_pending_invitations
from bot.services.matches import auto_draw_overdue_matches
from bot.services.notifications import notify_invitation_expired, notify_match_auto_draw


async def _expire_invitations_job(context) -> None:
    expired = expire_pending_invitations()
    for record in expired:
        await notify_invitation_expired(context, record.inviter, record.invitee, record.invitation)


async def _auto_draw_matches_job(context) -> None:
    matches = auto_draw_overdue_matches()
    for record in matches:
        await notify_match_auto_draw(context, record.fighter_a, record.fighter_b, record.match)


def register_jobs(application: Application) -> None:
    if application.job_queue is None:
        return
    application.job_queue.run_repeating(_expire_invitations_job, interval=3600, first=60, name='expire_invitations')
    application.job_queue.run_repeating(_auto_draw_matches_job, interval=3600, first=120, name='auto_draw_matches')
