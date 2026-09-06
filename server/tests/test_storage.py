from app import ids
from app.storage import repo

EXPECTED_TABLES = {
    "interviews",
    "capabilities",
    "transcript_segments",
    "code_snapshots",
    "test_runs",
    "claims",
    "evidence_links",
    "assessments",
    "findings",
    "finding_refs",
    "disputes",
    "session_events",
}


def make_interview(conn, **overrides):
    now = ids.now_iso()
    fields = {
        "id": ids.new_id("itv"),
        "display_name": "Ada Lovelace",
        "scenario_id": "document-search",
        "scenario_version": "v1",
        "consent_at": now,
        "expires_at": now,
        "state_json": "{}",
        "stage": "briefing",
        "active_role": "technical",
    }
    fields.update(overrides)
    return repo.create_interview(conn, **fields)


def test_schema_creates_all_tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {row["name"] for row in rows}
    assert EXPECTED_TABLES <= names


def test_create_interview_then_get_interview_round_trips(conn):
    created = make_interview(conn, display_name="Grace Hopper")

    fetched = repo.get_interview(conn, created["id"])

    assert fetched is not None
    assert fetched["id"] == created["id"]
    assert fetched["display_name"] == "Grace Hopper"
    assert fetched["status"] == "created"
    assert fetched["stage"] == "briefing"
    assert fetched["active_role"] == "technical"


def test_insert_segment_assigns_increasing_seq_per_interview_independently(conn):
    itv_a = make_interview(conn)
    itv_b = make_interview(conn)

    a1 = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=itv_a["id"], speaker="candidate",
        kind="turn", text="a1", stage="briefing", generation=0, status="complete",
    )
    b1 = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=itv_b["id"], speaker="candidate",
        kind="turn", text="b1", stage="briefing", generation=0, status="complete",
    )
    a2 = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=itv_a["id"], speaker="technical",
        kind="turn", text="a2", stage="briefing", generation=0, status="complete",
    )
    b2 = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=itv_b["id"], speaker="technical",
        kind="turn", text="b2", stage="briefing", generation=0, status="complete",
    )

    assert (a1["seq"], a2["seq"]) == (1, 2)
    assert (b1["seq"], b2["seq"]) == (1, 2)


def test_list_segments_limit_returns_last_n_in_ascending_order(conn):
    itv = make_interview(conn)
    for i in range(4):
        repo.insert_segment(
            conn, id=ids.new_id("seg"), interview_id=itv["id"], speaker="candidate",
            kind="turn", text=f"t{i}", stage="briefing", generation=0, status="complete",
        )

    last_two = repo.list_segments(conn, itv["id"], limit=2)

    assert [row["text"] for row in last_two] == ["t2", "t3"]
    assert last_two[0]["seq"] < last_two[1]["seq"]


def test_append_event_increasing_seq_and_list_events_filters(conn):
    itv = make_interview(conn)

    first = repo.append_event(conn, itv["id"], "stage_changed", {"stage": "briefing"})
    second = repo.append_event(conn, itv["id"], "stage_changed", {"stage": "investigation"})

    assert (first["seq"], second["seq"]) == (1, 2)

    after_first = repo.list_events(conn, itv["id"], first["seq"])

    assert [event["seq"] for event in after_first] == [second["seq"]]
    assert after_first[0]["payload"] == {"stage": "investigation"}


def test_delete_interview_rows_removes_rows_from_every_table(conn):
    itv = make_interview(conn)
    iid = itv["id"]

    repo.create_capability(conn, id=ids.new_id("cap"), interview_id=iid, kind="candidate", token_hash="hash-1")
    segment = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=iid, speaker="candidate",
        kind="turn", text="hi", stage="briefing", generation=0, status="complete",
    )
    snapshot = repo.insert_snapshot(
        conn, id=ids.new_id("snap"), interview_id=iid, files_json="{}", content_hash="hash", byte_size=10,
    )
    repo.insert_run(
        conn, id=ids.new_id("run"), interview_id=iid, snapshot_id=snapshot["id"],
        fixture_version="v1", check_version="v1", check_ids_json="[]", input_hash="hash",
        status="queued", executor="local",
    )
    claim = repo.insert_claim(
        conn, id=ids.new_id("clm"), interview_id=iid, segment_id=segment["id"],
        statement="statement", claim_type="diagnosis", scope="general", stage="briefing", clarity="clear",
    )
    repo.insert_link(
        conn, id=ids.new_id("lnk"), interview_id=iid, source_type="segment", source_id=segment["id"],
        target_type="claim", target_id=claim["id"], relation="supports",
    )
    assessment = repo.insert_assessment(
        conn, id=ids.new_id("asm"), interview_id=iid, status="pending",
        rubric_version="v1", prompt_version="v1", model_id="scripted-test-double", summary="",
    )
    finding = repo.insert_finding(
        conn, id=ids.new_id("fnd"), interview_id=iid, assessment_id=assessment["id"],
        dimension="understanding_problem", is_dimension=1, title="title",
        observation_level="demonstrated", explanation="explanation", assistance="assistance",
        uncertainty="uncertainty", follow_up="follow up", position=0,
    )
    repo.insert_finding_ref(conn, finding_id=finding["id"], ref_type="segment", ref_id=segment["id"], role="supports")
    repo.insert_dispute(
        conn, id=ids.new_id("dsp"), interview_id=iid, segment_id=segment["id"],
        original_text="original", proposed_text="proposed", reason="reason", affected_finding_ids_json="[]",
    )
    repo.append_event(conn, iid, "stage_changed", {"stage": "briefing"})

    repo.delete_interview_rows(conn, iid)

    assert repo.get_interview(conn, iid) is None
    assert repo.find_capability(conn, "hash-1") is None
    assert repo.list_segments(conn, iid) == []
    assert repo.list_snapshots(conn, iid) == []
    assert repo.list_runs(conn, iid) == []
    assert repo.list_claims(conn, iid) == []
    assert repo.list_links(conn, iid) == []
    assert repo.latest_assessment(conn, iid) is None
    assert repo.list_findings(conn, assessment["id"]) == []
    assert repo.list_finding_refs(conn, finding["id"]) == []
    assert repo.list_disputes(conn, iid) == []
    assert repo.list_events(conn, iid, 0) == []


def test_findings_referencing_finds_finding_by_ref(conn):
    itv = make_interview(conn)
    iid = itv["id"]
    segment = repo.insert_segment(
        conn, id=ids.new_id("seg"), interview_id=iid, speaker="candidate",
        kind="turn", text="hi", stage="briefing", generation=0, status="complete",
    )
    assessment = repo.insert_assessment(
        conn, id=ids.new_id("asm"), interview_id=iid, status="pending",
        rubric_version="v1", prompt_version="v1", model_id="scripted-test-double", summary="",
    )
    finding = repo.insert_finding(
        conn, id=ids.new_id("fnd"), interview_id=iid, assessment_id=assessment["id"],
        dimension="understanding_problem", is_dimension=1, title="title",
        observation_level="demonstrated", explanation="explanation", assistance="assistance",
        uncertainty="uncertainty", follow_up="follow up", position=0,
    )
    repo.insert_finding_ref(conn, finding_id=finding["id"], ref_type="segment", ref_id=segment["id"], role="supports")

    matches = repo.findings_referencing(conn, iid, "segment", segment["id"])

    assert [row["id"] for row in matches] == [finding["id"]]
