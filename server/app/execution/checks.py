"""Comparing what the sandbox returned against expectations the backend holds.

Document order is never significant: a step is satisfied when the returned ids
are the expected set. A check with a search-call budget must also stay inside
it, which is how the disabled-cache solution is told apart from a correct one.
"""

from dataclasses import dataclass

from app.scenario import Check


@dataclass
class StepResult:
    index: int
    op: str
    expected: list[str] | None
    actual: list[str] | None
    ok: bool | None
    error: str | None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "op": self.op,
            "expected": self.expected,
            "actual": self.actual,
            "ok": self.ok,
            "error": self.error,
        }


@dataclass
class CheckResult:
    check_id: str
    passed: bool
    steps: list[StepResult]
    search_calls: int | None
    max_search_calls: int | None
    efficiency_ok: bool | None
    error: str | None

    def to_dict(self) -> dict:
        return {
            "check_id": self.check_id,
            "passed": self.passed,
            "steps": [step.to_dict() for step in self.steps],
            "search_calls": self.search_calls,
            "max_search_calls": self.max_search_calls,
            "efficiency_ok": self.efficiency_ok,
            "error": self.error,
        }


def _step_result(index: int, step, raw: dict | None) -> StepResult:
    if raw is None:
        return StepResult(index, step.op, step.expect, None, None, None)
    error = raw.get("error")
    actual = raw.get("returned")
    if error is not None:
        ok = False
    elif step.expect is None:
        ok = True  # a revoke step only has to not raise
    else:
        ok = actual is not None and sorted(actual) == sorted(step.expect)
    return StepResult(index, step.op, step.expect, actual, ok, error)


def _evaluate_one(check: Check, raw: dict | None) -> CheckResult:
    if raw is None:
        return CheckResult(check.id, False, [], None, check.max_search_calls, None,
                           "the runner returned no result for this check")

    raw_steps = raw.get("steps") or []
    steps = [
        _step_result(index, step, raw_steps[index] if index < len(raw_steps) else None)
        for index, step in enumerate(check.steps)
    ]
    search_calls = raw.get("search_calls")
    error = raw.get("error")

    efficiency_ok = None
    if check.max_search_calls is not None:
        efficiency_ok = search_calls is not None and search_calls <= check.max_search_calls

    passed = error is None and efficiency_ok is not False and all(step.ok for step in steps)
    return CheckResult(check.id, passed, steps, search_calls, check.max_search_calls,
                       efficiency_ok, error)


def evaluate(checks: list[Check], parsed: dict) -> list[CheckResult]:
    by_id = {raw.get("check_id"): raw for raw in parsed.get("results", [])}
    return [_evaluate_one(check, by_id.get(check.id)) for check in checks]


def _comparable(results: list[dict]) -> dict:
    return {
        result.get("check_id"): (
            result.get("passed"),
            [
                None if step.get("actual") is None else sorted(step["actual"])
                for step in result.get("steps", [])
            ],
        )
        for result in results or []
    }


def results_differ(a: list[dict], b: list[dict]) -> bool:
    """Whether two result sets disagree on any check's outcome.

    Compares pass flags and returned document ids, the two things a reviewer
    would call a different outcome; ordering is ignored because evaluation
    ignores it too.
    """
    return _comparable(a) != _comparable(b)
