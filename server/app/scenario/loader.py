"""Loads a scenario package from disk into the Scenario dataclass.

A scenario package lives under `<scenario_root>/<scenario_id>/` with:
  application/           editable + read-only application source
  fixtures/<version>/    fixture JSON, one subdirectory per fixture version
  checks/<version>/      checks.json, runner.py, and reference solutions
  brief.md, rubric.json

The version directory names (the single subdirectory of fixtures/ and
checks/) become `fixture_version` and `check_version`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

EDITABLE_FILES = ["search.py", "cache.py", "permissions.py"]
READONLY_APPLICATION_FILES = ["index.py"]
FIXTURE_FILES = ["users.json", "documents.json", "permissions.json"]


@dataclass
class CheckStep:
    op: str  # "search" | "revoke"
    user: str
    query: str | None = None
    document: str | None = None
    expect: list[str] | None = None  # document ids, order-insensitive; None for revoke


@dataclass
class Check:
    id: str
    name: str
    description: str
    behavior: str
    introduced_at: str  # "initial" | "changed_condition"
    steps: list[CheckStep]
    max_search_calls: int | None = None


@dataclass
class Scenario:
    id: str
    version: str
    brief: str
    editable_files: dict[str, str]  # "search.py", "cache.py", "permissions.py"
    readonly_files: dict[str, str]  # "index.py", "runner.py", "fixtures/*.json"
    fixture_version: str  # "v1"
    check_version: str  # "v1"
    checks: list[Check]
    rubric: dict


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _single_subdir(path: Path) -> Path:
    subdirs = sorted(p for p in path.iterdir() if p.is_dir())
    if len(subdirs) != 1:
        raise ValueError(f"expected exactly one subdirectory under {path}, found {len(subdirs)}")
    return subdirs[0]


def _parse_step(raw: dict) -> CheckStep:
    return CheckStep(
        op=raw["op"],
        user=raw["user"],
        query=raw.get("query"),
        document=raw.get("document"),
        expect=raw.get("expect"),
    )


def _parse_check(raw: dict) -> Check:
    return Check(
        id=raw["id"],
        name=raw["name"],
        description=raw["description"],
        behavior=raw["behavior"],
        introduced_at=raw["introduced_at"],
        steps=[_parse_step(step) for step in raw["steps"]],
        max_search_calls=raw.get("max_search_calls"),
    )


def load_scenario(scenario_root: Path, scenario_id: str) -> Scenario:
    root = Path(scenario_root) / scenario_id
    application_dir = root / "application"

    editable_files = {name: _read(application_dir / name) for name in EDITABLE_FILES}

    fixture_dir = _single_subdir(root / "fixtures")
    checks_dir = _single_subdir(root / "checks")

    readonly_files = {name: _read(application_dir / name) for name in READONLY_APPLICATION_FILES}
    readonly_files["runner.py"] = _read(checks_dir / "runner.py")
    for name in FIXTURE_FILES:
        readonly_files[f"fixtures/{name}"] = _read(fixture_dir / name)

    checks_json = json.loads(_read(checks_dir / "checks.json"))
    checks = [_parse_check(raw) for raw in checks_json["checks"]]

    return Scenario(
        id=scenario_id,
        version=checks_dir.name,
        brief=_read(root / "brief.md"),
        editable_files=editable_files,
        readonly_files=readonly_files,
        fixture_version=fixture_dir.name,
        check_version=checks_dir.name,
        checks=checks,
        rubric=json.loads(_read(root / "rubric.json")),
    )


def public_check(check: Check, available: bool) -> dict:
    """CheckView: the candidate-facing projection of a Check, no expectations."""
    return {
        "id": check.id,
        "name": check.name,
        "description": check.description,
        "behavior": check.behavior,
        "introduced_at": check.introduced_at,
        "available": available,
    }
