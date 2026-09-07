"""The session-lifetime watchdog (PRD sections 4 and 15).

The controller ends a conversation at the cap on the next turn; a candidate who
stops talking, or a page that closed, sends no next turn while the paid voice
agent stays in the channel. This sweep runs on a timer and finishes every live
interview past the cap, paused time excluded, whether or not anyone speaks.
"""

import logging

from app.interview.controller import _elapsed_minutes
from app.storage import repo
from app.storage.events import emit

logger = logging.getLogger(__name__)


def list_live_interviews(conn):
    return conn.execute("SELECT * FROM interviews WHERE status = 'live'").fetchall()


def over_cap(row, cap_minutes: int) -> bool:
    return cap_minutes > 0 and _elapsed_minutes(row) >= cap_minutes


async def sweep_sessions(app) -> list[str]:
    """Finish every live interview past the session cap; returns the ids finished."""
    # Imported here: the routes module imports the controller this module leans on.
    from app.routes.interviews import complete_interview

    cap = app.state.settings.SESSION_CAP_MINUTES
    finished = []
    for row in list_live_interviews(app.state.db):
        if not over_cap(row, cap):
            continue
        interview_id = row["id"]
        emit(app.state.db, app.state.bus, interview_id, "session_cap_reached", {})
        try:
            await complete_interview(app, interview_id)
        except Exception:
            logger.exception("watchdog could not finish %s at the session cap", interview_id)
            continue
        finished.append(interview_id)
        logger.info("finished %s at the session cap", interview_id)
    return finished
