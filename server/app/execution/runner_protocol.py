"""The contract between the backend and the scenario's `runner.py`.

The runner is given a workspace directory and a JSON script on stdin, and
prints one JSON object describing what the candidate's code returned. It never
decides pass or fail: the expectations stay here, in `checks.py`.
"""

import hashlib
import json

from app.scenario import Check

STEP_KEYS = ("op", "user", "query", "document")


def build_workspace_files(scenario, snapshot_files: dict[str, str]) -> dict[str, str]:
    """Relative path -> content, laid out the way `runner.py` and `index.py` expect.

    Candidate files and `index.py`/`runner.py` sit at the top level; fixtures go
    under `fixtures/`, which is where `index.py` looks by default. Read-only
    files are applied last so a snapshot can never replace them.
    """
    files = dict(scenario.editable_files)
    files.update(
        {
            name: content
            for name, content in snapshot_files.items()
            if name in scenario.editable_files
        }
    )
    files.update(scenario.readonly_files)
    return files


def _script_step(step) -> dict:
    values = (step.op, step.user, step.query, step.document)
    return {key: value for key, value in zip(STEP_KEYS, values, strict=True) if value is not None}


def build_script(checks: list[Check]) -> str:
    """The runner's stdin JSON. Expectations are deliberately left out."""
    return json.dumps(
        {
            "checks": [
                {"id": check.id, "steps": [_script_step(step) for step in check.steps]}
                for check in checks
            ]
        }
    )


def parse_output(stdout: str) -> dict:
    """The last line of stdout that is a JSON object carrying `results`."""
    for line in reversed(stdout.strip().splitlines()):
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
            return parsed
    raise ValueError(f"no runner result object on stdout: {stdout[-500:]!r}")


def input_hash(scenario, snapshot_hash: str, check_ids: list[str],
               inputs_hash: str | None = None) -> str:
    """Identifies everything a run's outcome depends on, for replay comparison.

    `inputs_hash` is the content hash of the archived scenario inputs (see
    `archive.py`); with it, an edit under an unchanged version label changes
    the hash. `scenario` may be a `Scenario` or archived `RunInputs`.
    """
    digest = hashlib.sha256()
    parts = (scenario.fixture_version, scenario.check_version, snapshot_hash, *sorted(check_ids))
    if inputs_hash is not None:
        parts = (*parts, f"inputs:{inputs_hash}")
    for part in parts:
        digest.update(f"{part}\0".encode())
    return digest.hexdigest()
