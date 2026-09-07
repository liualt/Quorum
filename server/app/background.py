"""Background task bookkeeping: runs, follow-ups, and claim extraction all live here.

Every task is kept on `app.state.background_tasks` so tests can await them and
shutdown can cancel them, and every task logs its own failure rather than
leaving an unretrieved exception for the garbage collector to complain about.
"""

import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger(__name__)


def spawn(app, coro: Coroutine, what: str) -> asyncio.Task:
    tasks = getattr(app.state, "background_tasks", None)
    if tasks is None:
        tasks = set()
        app.state.background_tasks = tasks
    task = asyncio.create_task(_logged(coro, what))
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


async def _logged(coro: Coroutine, what: str) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("%s failed", what)


async def cancel_all(app) -> None:
    """Stop whatever is still running; called from the lifespan's shutdown."""
    tasks = [task for task in getattr(app.state, "background_tasks", ()) if not task.done()]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
