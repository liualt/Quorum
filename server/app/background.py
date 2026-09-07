"""Background task bookkeeping: runs, follow-ups, claim extraction, and expiry all live here.

Every one-off task is kept on `app.state.background_tasks` so tests and `/finish`
can await the work in flight and shutdown can cancel it, and every task logs its
own failure rather than leaving an unretrieved exception for the garbage
collector to complain about. A periodic task never finishes, so it is kept apart
on `app.state.periodic_tasks`: awaiting "everything in flight" must not wait for
next hour's expiry sweep.
"""

import asyncio
import logging
from collections.abc import Callable, Coroutine

logger = logging.getLogger(__name__)


def spawn(app, coro: Coroutine, what: str) -> asyncio.Task:
    """Run `coro` in the background; `what` names it for logs and for `pending`."""
    tasks = _tasks(app, "background_tasks")
    task = asyncio.create_task(_logged(coro, what), name=what)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def pending(app, prefix: str) -> list[asyncio.Task]:
    """The unfinished background tasks whose name starts with `prefix`."""
    return [
        task
        for task in getattr(app.state, "background_tasks", ())
        if not task.done() and task.get_name().startswith(prefix)
    ]


def spawn_periodic(
    app, make_coro: Callable[[], Coroutine], interval_seconds: float, what: str
) -> asyncio.Task:
    """Run `make_coro()` every `interval_seconds` until shutdown, starting after one interval."""
    tasks = _tasks(app, "periodic_tasks")
    task = asyncio.create_task(_periodic(make_coro, interval_seconds, what), name=what)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def _tasks(app, attribute: str) -> set:
    tasks = getattr(app.state, attribute, None)
    if tasks is None:
        tasks = set()
        setattr(app.state, attribute, tasks)
    return tasks


async def _logged(coro: Coroutine, what: str) -> None:
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("%s failed", what)


async def _periodic(make_coro: Callable[[], Coroutine], interval_seconds: float, what: str) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        await _logged(make_coro(), what)


async def cancel_all(app) -> None:
    """Stop whatever is still running; called from the lifespan's shutdown."""
    tasks = [
        task
        for attribute in ("background_tasks", "periodic_tasks")
        for task in getattr(app.state, attribute, ())
        if not task.done()
    ]
    for task in tasks:
        task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
