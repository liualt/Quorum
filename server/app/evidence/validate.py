"""Checks on the assessment the model returned, before any of it becomes a record.

Pure: a connection to look ids up, a payload in, error strings out. Every ref
must name a record of this interview (PRD section 10: evidence relationships are
validated references, not model-generated connections), and the text must stay
inside what the product promises never to say (PRD section 6: no score, no
ranking, no personality, no honesty verdict).
"""

import re

from app.interview.prompts import DIMENSIONS
from app.storage import repo

OBSERVATION_LEVELS = ("demonstrated", "partly_demonstrated", "not_observed")
REF_TYPES = ("segment", "run", "claim", "snapshot")
MAX_FINDINGS = 6
MIN_EXPLANATION_CHARS = 20
# Whole words with their inflections: "scores" and "ranked" are the same promise
# broken; "underscored" and "frank" are not.
FORBIDDEN_STEMS = (
    r"scor(?:e|es|ed|ing)",
    r"rank(?:s|ed|ing)?",
    r"personalit(?:y|ies)",
    r"honest(?:ly)?",
    r"dishonest(?:ly)?",
)
TEXT_FIELDS = ("title", "explanation", "assistance", "uncertainty", "follow_up")
REF_FIELDS = ("supporting_refs", "opposing_refs")

_FORBIDDEN = re.compile(r"\b(?:" + "|".join(FORBIDDEN_STEMS) + r")\b", re.IGNORECASE)
_GETTERS = {
    "segment": repo.get_segment,
    "run": repo.get_run,
    "claim": repo.get_claim,
    "snapshot": repo.get_snapshot,
}


def validate_assessment_payload(conn, interview_id: str, payload) -> list[str]:
    """Every reason the payload cannot be stored as an assessment; empty when it can."""
    if not isinstance(payload, dict):
        return ["the response is not a JSON object"]
    errors = []

    summary = payload.get("summary")
    if isinstance(summary, str):
        errors.extend(_forbidden("summary", summary))
    else:
        errors.append("summary must be a string")

    dimensions = payload.get("dimensions")
    if not isinstance(dimensions, list):
        errors.append("dimensions must be a list")
        dimensions = []
    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings must be a list")
        findings = []

    errors.extend(_dimension_coverage(dimensions))
    if len(findings) > MAX_FINDINGS:
        errors.append(f"{len(findings)} findings returned; at most {MAX_FINDINGS} are allowed")
    for index, entry in enumerate(dimensions):
        errors.extend(_entry_errors(conn, interview_id, f"dimensions[{index}]", entry, check_dimension=False))
    for index, entry in enumerate(findings):
        errors.extend(_entry_errors(conn, interview_id, f"findings[{index}]", entry, check_dimension=True))
    return errors


def _dimension_coverage(dimensions: list) -> list[str]:
    """Exactly one entry per dimension, and no entry for anything else."""
    names = [entry.get("dimension") for entry in dimensions if isinstance(entry, dict)]
    errors = []
    for dimension in DIMENSIONS:
        count = names.count(dimension)
        if count == 0:
            errors.append(f"dimension {dimension!r} is missing")
        elif count > 1:
            errors.append(f"dimension {dimension!r} appears {count} times")
    errors.extend(f"unexpected dimension {name!r}" for name in names if name not in DIMENSIONS)
    return errors


def _entry_errors(conn, interview_id: str, where: str, entry, *, check_dimension: bool) -> list[str]:
    if not isinstance(entry, dict):
        return [f"{where} is not an object"]
    errors = []
    if check_dimension and entry.get("dimension") not in DIMENSIONS:
        errors.append(f"{where}: unexpected dimension {entry.get('dimension')!r}")
    level = entry.get("observation_level")
    if level not in OBSERVATION_LEVELS:
        errors.append(f"{where}: invalid observation_level {level!r}")
    explanation = entry.get("explanation")
    if not isinstance(explanation, str) or len(explanation.strip()) < MIN_EXPLANATION_CHARS:
        errors.append(f"{where}: explanation is shorter than {MIN_EXPLANATION_CHARS} characters")
    for field in TEXT_FIELDS:
        value = entry.get(field)
        if isinstance(value, str):
            errors.extend(_forbidden(f"{where}.{field}", value))
    for field in REF_FIELDS:
        refs = entry.get(field)
        if not isinstance(refs, list):
            errors.append(f"{where}: {field} must be a list")
            continue
        for ref in refs:
            errors.extend(_ref_errors(conn, interview_id, f"{where}.{field}", ref))
    return errors


def _ref_errors(conn, interview_id: str, where: str, ref) -> list[str]:
    if not isinstance(ref, dict):
        return [f"{where}: ref is not an object"]
    ref_type, ref_id = ref.get("type"), ref.get("id")
    if ref_type not in REF_TYPES:
        return [f"{where}: unknown ref type {ref_type!r}"]
    if not isinstance(ref_id, str) or not _exists(conn, interview_id, ref_type, ref_id):
        return [f"{where}: {ref_type} {ref_id!r} is not a record of this interview"]
    return []


def _exists(conn, interview_id: str, ref_type: str, ref_id: str) -> bool:
    row = _GETTERS[ref_type](conn, ref_id)
    return row is not None and row["interview_id"] == interview_id


def _forbidden(where: str, text: str) -> list[str]:
    match = _FORBIDDEN.search(text)
    return [f"{where} contains the word {match.group(0)!r}"] if match else []
