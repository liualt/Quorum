#!/usr/bin/env python3
"""Prove a running Quorum backend still executes the scenario correctly.

Creates an interview over HTTP, starts it, saves the scenario's seeded code
unchanged, runs every check that is available at the briefing stage, and prints
the pass matrix with the executor that produced it. The seeded application has
the defect the interview is about, so the outcome is known in advance: this
exits non-zero when the matrix does not match it, or when anything on the way
there fails.

    python3 scripts/smoke_test.py --base http://localhost:8000 --origin http://localhost:3000

Standard library only, so it runs against a deployed backend from any machine
with a `python3` on it. `QUORUM_BASE_URL` and `QUORUM_WEB_ORIGIN` set the
defaults for the two arguments.
"""

import argparse
import sys
import time

from quorum_api import ApiError, Client, default_base_url, default_web_origin

#: What the seeded application does with the checks available before the
#: changed condition (`server/tests/test_checks_matrix.py` pins the same table).
#: The cache is keyed by query alone, so one company reads another's results.
EXPECTED_SEEDED = {
    "access_filtering": True,
    "cross_company_isolation": False,
    "repeat_search_efficiency": False,
}

RUN_POLL_SECONDS = 0.5
RUN_POLL_TIMEOUT_SECONDS = 120.0
TERMINAL_STATUSES = ("completed", "timeout", "failed", "unavailable")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=default_base_url(), help="backend base URL")
    parser.add_argument("--origin", default=default_web_origin(), help="allowed web origin")
    args = parser.parse_args(argv)

    client = Client(args.base, args.origin)
    try:
        return smoke(client)
    except ApiError as error:
        print(f"FAIL  {error}")
        return 1


def smoke(client: Client) -> int:
    health = client.get("/api/health")
    print(
        "GET /api/health  "
        f"status={health['status']} executor={health['executor']} "
        f"llm_provider={health['llm_provider']} llm_model={health['llm_model']} "
        f"voice_enabled={health['voice_enabled']}"
    )

    created = client.post(
        "/api/interviews", {"display_name": "Smoke test", "consent": True}
    )
    interview_id = created["id"]
    print(f"created interview {interview_id}")

    client.post(f"/api/interviews/{interview_id}/start")
    view = client.get(f"/api/interviews/{interview_id}")
    print(f"started; stage={view['stage']} voice_enabled={view['voice_enabled']}")

    seeded = view["scenario"]["editable_files"]
    saved = client.put(f"/api/interviews/{interview_id}/files", {"files": seeded})
    print(
        f"saved {len(seeded)} seeded files as {saved['snapshot_id']} "
        f"({saved['content_hash'][:12]})"
    )

    available = [check["id"] for check in view["scenario"]["checks"] if check["available"]]
    print(f"running {len(available)} available checks: {', '.join(available)}")
    started = client.post(
        f"/api/interviews/{interview_id}/runs",
        {"snapshot_id": saved["snapshot_id"], "check_ids": available},
    )
    run = poll_run(client, interview_id, started["id"])

    return report(run, available)


def poll_run(client: Client, interview_id: str, run_id: str) -> dict:
    """The run once it reaches a terminal status, or a RuntimeError saying it did not."""
    deadline = time.monotonic() + RUN_POLL_TIMEOUT_SECONDS
    while True:
        run = client.get(f"/api/interviews/{interview_id}/runs/{run_id}")
        if run["status"] in TERMINAL_STATUSES:
            return run
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"FAIL  run {run_id} was still {run['status']} after "
                f"{RUN_POLL_TIMEOUT_SECONDS:.0f}s"
            )
        time.sleep(RUN_POLL_SECONDS)


def report(run: dict, requested: list[str]) -> int:
    """Print the pass matrix and say whether it is the one the seeded code earns."""
    print(f"\nrun {run['id']}  status={run['status']}  executor={run['executor']}")
    if run["status"] != "completed":
        print(f"FAIL  the run did not complete: {run['stderr_excerpt'] or 'no output'}")
        return 1

    observed = {result["check_id"]: bool(result["passed"]) for result in run["results"] or []}
    problems = []
    print(f"\n{'check':<28} {'result':<8} expected")
    for check_id in requested:
        expected = EXPECTED_SEEDED.get(check_id)
        actual = observed.get(check_id)
        if actual is None:
            problems.append(f"{check_id}: the run returned no result for it")
            print(f"{check_id:<28} {'MISSING':<8} {_word(expected)}")
            continue
        if expected is None:
            problems.append(f"{check_id}: this script has no expectation for it")
            print(f"{check_id:<28} {_word(actual):<8} unknown")
            continue
        if actual != expected:
            problems.append(f"{check_id}: expected {_word(expected)}, got {_word(actual)}")
        print(f"{check_id:<28} {_word(actual):<8} {_word(expected)}")

    print(
        f"\nfixtures {run['fixture_version']} · checks {run['check_version']} · "
        f"input hash {run['input_hash'][:16]} · ran on the {run['executor']} executor"
    )
    if problems:
        for problem in problems:
            print(f"FAIL  {problem}")
        return 1
    print("\nOK  the seeded application produced the matrix it is meant to produce.")
    return 0


def _word(passed: bool | None) -> str:
    return "unknown" if passed is None else ("pass" if passed else "fail")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
