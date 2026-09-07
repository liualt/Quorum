"""In-process pub/sub for interview session events, backed by session_events."""

import asyncio

from app.storage import repo


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, interview_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(interview_id, []).append(queue)
        return queue

    def unsubscribe(self, interview_id: str, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(interview_id)
        if not queues:
            return
        if queue in queues:
            queues.remove(queue)
        if not queues:
            self._subscribers.pop(interview_id, None)

    def publish(self, interview_id: str, event: dict) -> None:
        for queue in self._subscribers.get(interview_id, []):
            queue.put_nowait(event)


def emit(conn, bus: EventBus, interview_id: str, type: str, payload: dict) -> dict:
    event = repo.append_event(conn, interview_id, type, payload)
    bus.publish(interview_id, event)
    return event
