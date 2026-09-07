from app import ids
from app.storage import repo
from app.storage.events import EventBus, emit


def make_interview(conn):
    now = ids.now_iso()
    return repo.create_interview(
        conn,
        id=ids.new_id("itv"),
        display_name="Ada Lovelace",
        scenario_id="document-search",
        scenario_version="v1",
        consent_at=now,
        expires_at=now,
        state_json="{}",
        stage="briefing",
        active_role="technical",
    )


def test_emit_publishes_to_two_subscribers_and_persists(conn):
    bus = EventBus()
    itv = make_interview(conn)

    queue_a = bus.subscribe(itv["id"])
    queue_b = bus.subscribe(itv["id"])

    event = emit(conn, bus, itv["id"], "stage_changed", {"stage": "investigation"})

    assert event["type"] == "stage_changed"
    assert event["payload"] == {"stage": "investigation"}
    assert queue_a.get_nowait() == event
    assert queue_b.get_nowait() == event

    persisted = repo.list_events(conn, itv["id"], 0)
    assert persisted == [event]


def test_unsubscribe_stops_delivery(conn):
    bus = EventBus()
    itv = make_interview(conn)

    queue = bus.subscribe(itv["id"])
    bus.unsubscribe(itv["id"], queue)

    emit(conn, bus, itv["id"], "stage_changed", {"stage": "investigation"})

    assert queue.empty()
