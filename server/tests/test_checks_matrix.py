"""The pass matrix: LocalExecutor over the seeded application and the three
reference solutions, evaluated through the real workspace layout and script.

This is the test that pins what "passed" means for every check, so a change to
the runner protocol, the workspace layout, or the evaluation rules has to
account for the behaviour each reference solution is meant to demonstrate.
"""

import time
from pathlib import Path

import pytest

from app.execution.checks import evaluate, results_differ
from app.execution.executor import LocalExecutor
from app.execution.runner_protocol import (
    build_script,
    build_workspace_files,
    input_hash,
    parse_output,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_CAP = 65536

PASS_MATRIX = {
    "seeded": {
        "access_filtering": True,
        "cross_company_isolation": False,
        "revocation_next_request": False,
        "repeat_search_efficiency": False,
    },
    "partial": {
        "access_filtering": True,
        "cross_company_isolation": True,
        "revocation_next_request": False,
        "repeat_search_efficiency": True,
    },
    "complete": {
        "access_filtering": True,
        "cross_company_isolation": True,
        "revocation_next_request": True,
        "repeat_search_efficiency": True,
    },
    "disabled": {
        "access_filtering": True,
        "cross_company_isolation": True,
        "revocation_next_request": True,
        "repeat_search_efficiency": False,
    },
}


def solution_files(scenario, variant):
    """The snapshot a candidate would have saved to reach `variant`."""
    if variant == "seeded":
        return {}
    path = (
        REPO_ROOT
        / "scenarios"
        / scenario.id
        / "checks"
        / scenario.check_version
        / "solutions"
        / variant
        / "search.py"
    )
    return {"search.py": path.read_text(encoding="utf-8")}


async def run_checks(scenario, snapshot_files, *, checks=None, timeout_s=60):
    checks = scenario.checks if checks is None else checks
    workspace = build_workspace_files(scenario, snapshot_files)
    result = await LocalExecutor().run(
        workspace, build_script(checks), timeout_s=timeout_s, output_cap=OUTPUT_CAP
    )
    assert result.status == "completed", result.stderr
    results = evaluate(checks, parse_output(result.stdout))
    return {item.check_id: item for item in results}


@pytest.mark.parametrize("variant", sorted(PASS_MATRIX))
async def test_pass_matrix(scenario, variant):
    results = await run_checks(scenario, solution_files(scenario, variant))

    assert {check_id: item.passed for check_id, item in results.items()} == PASS_MATRIX[variant]


async def test_disabled_cache_fails_only_on_the_search_call_budget(scenario):
    results = await run_checks(scenario, solution_files(scenario, "disabled"))

    efficiency = results["repeat_search_efficiency"]
    assert efficiency.search_calls == 3
    assert efficiency.max_search_calls == 2
    assert efficiency.efficiency_ok is False
    assert all(step.ok for step in efficiency.steps)
    assert efficiency.passed is False


async def test_seeded_cross_company_step_records_the_leaked_document(scenario):
    checks = [c for c in scenario.checks if c.id == "cross_company_isolation"]
    results = await run_checks(scenario, {}, checks=checks)

    step = results["cross_company_isolation"].steps[1]
    assert step.expected == ["doc_birch_q3"]
    assert step.actual == ["doc_acme_q3"]
    assert step.ok is False
    assert step.error is None


async def test_search_that_raises_fails_the_check_without_raising(scenario):
    checks = [c for c in scenario.checks if c.id == "access_filtering"]
    results = await run_checks(scenario, {"search.py": "raise RuntimeError('boom')\n"}, checks=checks)

    result = results["access_filtering"]
    assert result.passed is False
    assert result.error is not None
    assert "boom" in result.error


async def test_endless_loop_is_reported_as_a_timeout(scenario):
    checks = [c for c in scenario.checks if c.id == "access_filtering"]
    workspace = build_workspace_files(scenario, {"search.py": "while True:\n    pass\n"})

    started = time.monotonic()
    result = await LocalExecutor().run(
        workspace, build_script(checks), timeout_s=2, output_cap=OUTPUT_CAP
    )
    elapsed = time.monotonic() - started

    assert result.status == "timeout"
    # The runner's own per-check timeout is 8 s; ours has to fire first.
    assert elapsed < 7


def test_workspace_layout_matches_what_the_runner_expects(scenario):
    workspace = build_workspace_files(scenario, {"search.py": "# candidate\n"})

    assert workspace["search.py"] == "# candidate\n"
    assert workspace["cache.py"] == scenario.editable_files["cache.py"]
    assert workspace["runner.py"] == scenario.readonly_files["runner.py"]
    assert "fixtures/users.json" in workspace
    assert set(workspace) == set(scenario.editable_files) | set(scenario.readonly_files)


def test_read_only_files_cannot_be_replaced_by_a_snapshot(scenario):
    workspace = build_workspace_files(scenario, {"index.py": "SEARCH_CALLS = 0\n"})

    assert workspace["index.py"] == scenario.readonly_files["index.py"]


def test_parse_output_takes_the_last_json_line(scenario):
    parsed = parse_output('noise\n{"results": []}\n')

    assert parsed == {"results": []}


def test_parse_output_rejects_output_without_a_results_object():
    with pytest.raises(ValueError):
        parse_output("Traceback (most recent call last):\n  ImportError\n")


def test_input_hash_is_stable_across_check_id_order(scenario):
    first = input_hash(scenario, "hash-a", ["b_check", "a_check"])
    second = input_hash(scenario, "hash-a", ["a_check", "b_check"])
    third = input_hash(scenario, "hash-b", ["a_check", "b_check"])

    assert first == second
    assert first != third


def test_results_differ_compares_pass_flags_and_returned_ids():
    base = [{"check_id": "a", "passed": True, "steps": [{"actual": ["d1", "d2"]}]}]
    reordered = [{"check_id": "a", "passed": True, "steps": [{"actual": ["d2", "d1"]}]}]
    changed = [{"check_id": "a", "passed": True, "steps": [{"actual": ["d1"]}]}]
    failed = [{"check_id": "a", "passed": False, "steps": [{"actual": ["d1", "d2"]}]}]

    assert results_differ(base, reordered) is False
    assert results_differ(base, changed) is True
    assert results_differ(base, failed) is True
    assert results_differ(base, []) is True
