"""Deleting an interview, on request or when its retention runs out (PRD section 12).

One path for both: the voice agent is stopped while its id can still be read,
then every row and the snapshot directory go. Expiry is the same deletion
applied to every interview past its `expires_at`; the lifespan runs it once at
startup and then on an hourly timer.
"""

import asyncio
import logging

from app import background
from app.storage import repo, snapshots

logger = logging.getLogger(__name__)

EXPIRY_INTERVAL_SECONDS = 3600.0
VOICE_STOP_TIMEOUT_SECONDS = 10.0


async def delete_interview(app, interview_id: str) -> None:
    """Remove every trace of an interview: its agent, its rows, its snapshots."""
    # Same lock order as finish: don't remove evidence while its report is saved.
    finish_lock = app.state.finish_locks.setdefault(interview_id, asyncio.Lock())
    async with finish_lock, app.state.controller.interview_lock(interview_id):
        row = repo.get_interview(app.state.db, interview_id)
        if row is None:
            return
        repo.update_interview(app.state.db, interview_id, status="deleted")
        await background.cancel_interview(app, interview_id)
        voice = getattr(app.state, "voice", None)
        if row["agora_agent_id"] and voice is not None:
            try:
                await asyncio.wait_for(voice.stop_agent(row["agora_agent_id"]), VOICE_STOP_TIMEOUT_SECONDS)
            except Exception:
                logger.warning("voice stop failed during deletion of %s", interview_id)
        repo.delete_interview_rows(app.state.db, interview_id)
        snapshots.delete_interview_dir(app.state.settings.SNAPSHOT_DIR, interview_id)


async def expire_interviews(app, now_iso: str) -> int:
    """Delete every interview whose retention ended before `now_iso`; returns how many."""
    rows = repo.list_expired_interviews(app.state.db, now_iso)
    for row in rows:
        await delete_interview(app, row["id"])
    if rows:
        logger.info("expired %d interview(s)", len(rows))
    return len(rows)
