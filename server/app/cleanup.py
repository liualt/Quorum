"""Deleting an interview, on request or when its retention runs out (PRD section 12).

One path for both: the voice agent is stopped while its id can still be read,
then every row and the snapshot directory go. Expiry is the same deletion
applied to every interview past its `expires_at`; the lifespan runs it once at
startup and then on an hourly timer.
"""

import logging

from app.storage import repo, snapshots

logger = logging.getLogger(__name__)

EXPIRY_INTERVAL_SECONDS = 3600.0


async def delete_interview(app, interview_id: str) -> None:
    """Remove every trace of an interview: its agent, its rows, its snapshots."""
    row = repo.get_interview(app.state.db, interview_id)
    voice = getattr(app.state, "voice", None)
    if row is not None and row["agora_agent_id"] and voice is not None:
        # `stop_agent` never raises, so a deletion is never blocked by Agora.
        await voice.stop_agent(row["agora_agent_id"])
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
