"""Tests for the document-search scenario package and its loader."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.scenario.loader import load_scenario, public_check

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_ROOT = REPO_ROOT / "scenarios"
SCENARIO_DIR = SCENARIO_ROOT / "document-search"

EXPECTED_CHECK_IDS = [
    "access_filtering",
    "cross_company_isolation",
    "revocation_next_request",
    "repeat_search_efficiency",
]


@pytest.fixture
def scenario():
    return load_scenario(SCENARIO_ROOT, "document-search")


def test_loads_editable_files(scenario):
    assert set(scenario.editable_files) == {"search.py", "cache.py", "permissions.py"}
    for content in scenario.editable_files.values():
        assert content.strip()


def test_loads_readonly_files(scenario):
    assert set(scenario.readonly_files) == {
        "index.py",
        "runner.py",
        "fixtures/users.json",
        "fixtures/documents.json",
        "fixtures/permissions.json",
    }
    for content in scenario.readonly_files.values():
        assert content.strip()


def test_versions_come_from_directory_names(scenario):
    assert scenario.fixture_version == "v1"
    assert scenario.check_version == "v1"


def test_checks_loaded(scenario):
    assert [check.id for check in scenario.checks] == EXPECTED_CHECK_IDS


def test_check_steps_parsed(scenario):
    access = next(c for c in scenario.checks if c.id == "access_filtering")
    assert [s.op for s in access.steps] == ["search", "search", "search"]
    assert access.steps[0].user == "u_alice"
    assert access.steps[0].query == "quarterly"
    assert access.steps[0].expect == ["doc_acme_q3", "doc_acme_forecast"]

    revocation = next(c for c in scenario.checks if c.id == "revocation_next_request")
    revoke_step = revocation.steps[1]
    assert revoke_step.op == "revoke"
    assert revoke_step.document == "doc_acme_forecast"
    assert revoke_step.expect is None

    efficiency = next(c for c in scenario.checks if c.id == "repeat_search_efficiency")
    assert efficiency.max_search_calls == 2
    assert access.max_search_calls is None


def test_rubric_and_brief_loaded(scenario):
    assert scenario.rubric["version"] == "v1"
    assert len(scenario.rubric["dimensions"]) == 4
    assert "document search" in scenario.brief.lower()


def test_public_check_omits_expectations(scenario):
    check = next(c for c in scenario.checks if c.id == "access_filtering")
    view = public_check(check, available=True)
    assert view == {
        "id": "access_filtering",
        "name": check.name,
        "description": check.description,
        "behavior": check.behavior,
        "introduced_at": "initial",
        "available": True,
    }
    assert "steps" not in view
    assert "expect" not in view


def _script_from_checks(checks):
    """Build the runner's stdin JSON with steps stripped of `expect`."""
    return json.dumps(
        {
            "checks": [
                {
                    "id": check.id,
                    "steps": [
                        {
                            k: v
                            for k, v in {
                                "op": step.op,
                                "user": step.user,
                                "query": step.query,
                                "document": step.document,
                            }.items()
                            if v is not None
                        }
                        for step in check.steps
                    ],
                }
                for check in checks
            ]
        }
    )


@pytest.fixture
def sandbox(tmp_path, scenario):
    """Assemble a sandbox dir the way the executor would: seeded application
    files plus index.py and runner.py (read-only) and a fixtures/ subdir."""
    application_dir = SCENARIO_DIR / "application"
    for name in ["search.py", "cache.py", "permissions.py", "index.py"]:
        shutil.copy(application_dir / name, tmp_path / name)

    runner_src = SCENARIO_DIR / "checks" / scenario.check_version / "runner.py"
    shutil.copy(runner_src, tmp_path / "runner.py")

    fixtures_dst = tmp_path / "fixtures"
    fixtures_dst.mkdir()
    fixtures_src = SCENARIO_DIR / "fixtures" / scenario.fixture_version
    for name in ["users.json", "documents.json", "permissions.json"]:
        shutil.copy(fixtures_src / name, fixtures_dst / name)

    return tmp_path


def test_runner_against_seeded_application_reveals_the_bug(sandbox, scenario):
    script = _script_from_checks(scenario.checks)

    proc = subprocess.run(
        [sys.executable, "runner.py"],
        input=script,
        capture_output=True,
        text=True,
        cwd=sandbox,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    output = json.loads(proc.stdout.strip().splitlines()[-1])
    results = {r["check_id"]: r for r in output["results"]}

    # The seeded cache keys only on the normalised query, so Carol (Birch)
    # gets back Alice's (Acme) cached result for an identical query.
    cross = results["cross_company_isolation"]
    assert cross["error"] is None
    assert cross["steps"][1]["returned"] == ["doc_acme_q3"]

    access = results["access_filtering"]
    assert access["error"] is None
    assert access["steps"][0]["returned"] == ["doc_acme_q3", "doc_acme_forecast"]
    assert access["steps"][1]["returned"] == ["doc_acme_onboarding"]
    assert access["steps"][2]["returned"] == []
