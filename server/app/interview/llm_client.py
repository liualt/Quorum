"""The one model client: an OpenAI-compatible implementation and a test double.

`OpenAICompatibleClient` is what runs in production; `ScriptedLLM` exists only so
tests and the offline demo can drive the controller without a network or an API
key. The double never sees a real model: it reads the machine-readable blocks
`app.interview.prompts` writes into every system prompt and answers from small
keyword tables, so its output is deterministic and asserted on by the controller
and end-to-end tests.
"""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

import httpx2
import openai

from app.config import Settings
from app.interview import prompts


class LLMError(Exception):
    """Any failure to get a usable answer out of the model."""


class LLMClient(Protocol):
    model_id: str

    def stream_text(
        self, messages: list[dict], *, temperature: float = 0.4, max_tokens: int = 220
    ) -> AsyncIterator[str]: ...

    async def complete_json(self, messages: list[dict], *, max_tokens: int = 1500) -> dict: ...


class OpenAICompatibleClient:
    """Chat completions against any OpenAI-compatible endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str, http_client=None):
        self.model_id = model
        self._client = openai.AsyncOpenAI(
            base_url=base_url, api_key=api_key, http_client=http_client
        )

    async def stream_text(
        self, messages: list[dict], *, temperature: float = 0.4, max_tokens: int = 220
    ) -> AsyncIterator[str]:
        try:
            stream = await self._client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                stream=True,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            async for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except (openai.OpenAIError, httpx2.HTTPError) as error:
            raise LLMError(f"streaming completion failed: {error}") from error

    async def complete_json(self, messages: list[dict], *, max_tokens: int = 1500) -> dict:
        try:
            response = await self._client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=0,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
        except (openai.OpenAIError, httpx2.HTTPError) as error:
            raise LLMError(f"json completion failed: {error}") from error

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise LLMError("the model returned an empty completion")
        try:
            return json.loads(content)
        except json.JSONDecodeError as error:
            raise LLMError(f"the model returned invalid JSON: {error}") from error


# --- the scripted test double -----------------------------------------------------

SCENARIO_NOTICE_TEXT = (
    "Customer administrator here. I just removed an employee's access to a document. "
    "Can they still retrieve it from a search they ran earlier?"
)
HINT_PREFIX = "Here is a narrower question:"
INVALID_REFS_MARKER = "[[scripted:invalid-refs]]"

# Keyword tables. Order matters only for which claim comes first.
CLAIM_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (
        ("cache key", "keyed by", "query only", "same key", "shared cache", "leak",
         "other company", "cross"),
        "diagnosis",
        "cross_company",
    ),
    (("revoke", "revocation", "permission change", "stale"), "diagnosis", "revocation"),
    (
        ("ship", "don't ship", "block the release", "roll back", "disable the cache", "hold"),
        "release_decision",
        "general",
    ),
    (("test", "check", "assert"), "test_plan", "general"),
)
VAGUE_WORDS = ("not sure", "maybe", "might", "i think", "unclear")
REVISION_WORDS = ("actually", "i was wrong", "changed my mind")

COVERED_KEYS = (
    "initial_explanation",
    "release_decision",
    "cross_company",
    "revocation",
    "final_recommendation",
)


@dataclass(frozen=True)
class DimensionEvidence:
    """What the double treats as evidence for one assessment dimension."""

    check_id: str | None
    scopes: tuple[str, ...]
    claim_types: tuple[str, ...]
    title: str


DIMENSION_EVIDENCE = {
    "understanding_problem": DimensionEvidence(
        "cross_company_isolation", ("cross_company",), ("diagnosis",),
        "Explained the cross-company cache leak",
    ),
    "implementing_checking_fix": DimensionEvidence(
        "access_filtering", ("access", "efficiency"), ("fix_description", "test_plan"),
        "Changed the code and ran the checks",
    ),
    "explaining_consequences": DimensionEvidence(
        None, ("general",), ("release_decision",),
        "Stated a release decision and its cost",
    ),
    "responding_to_new_evidence": DimensionEvidence(
        "revocation_next_request", ("revocation",), (),
        "Revised after the changed condition",
    ),
}

EXPANDED_FINDINGS = (
    ("understanding_problem", "The cache key covered only the query"),
    ("implementing_checking_fix", "The checks were run against a saved snapshot"),
)


def _system_text(messages: list[dict]) -> str:
    for message in messages:
        if message.get("role") == "system":
            return message.get("content") or ""
    return ""


def _user_text(messages: list[dict]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return message.get("content") or ""
    return ""


def _require_task(messages: list[dict], expected: str) -> str:
    task = prompts.read_task(messages)
    if task != expected:
        raise LLMError(f"the scripted double cannot answer a {task!r} prompt as {expected!r}")
    return _system_text(messages)


def _instruction_kind(system: str) -> str:
    block = prompts.read_block(system, prompts.BLOCK_INSTRUCTION) or "kind: normal"
    return block.removeprefix("kind:").strip()


def _run_sentence(digest: dict) -> str:
    failed = digest.get("failed_checks") or []
    if failed:
        return f"I looked at your latest run, and it failed {', '.join(failed)}."
    passed = digest.get("passed_checks") or []
    return f"I looked at your latest run, and it passed {', '.join(passed) or 'every check'}."


def scripted_spoken_turn(system: str) -> str:
    """The double's spoken turn: role label, instruction kind, and the pending run."""
    kind = _instruction_kind(system)
    if kind == "scenario_notice":
        return SCENARIO_NOTICE_TEXT

    role = prompts.read_block(system, prompts.BLOCK_ROLE) or "technical"
    parts = []
    if kind == "hint":
        parts.append(HINT_PREFIX)
    parts.append(f"{prompts.ROLE_LABELS.get(role, role)} here, on a {kind} turn.")
    pending = prompts.read_json_block(system, prompts.BLOCK_PENDING_RUNS, default=[]) or []
    if pending:
        parts.append(_run_sentence(pending[-1]))
    parts.append("What would you check next?")
    return " ".join(parts)


def scripted_claims(system: str, candidate_text: str) -> dict:
    """The double's claim extraction: keyword tables over the candidate's words."""
    lowered = candidate_text.lower()
    stage = prompts.read_block(system, prompts.BLOCK_STAGE) or ""
    prior = prompts.read_json_block(system, prompts.BLOCK_PRIOR_CLAIMS, default=[]) or []
    clarity = "vague" if any(word in lowered for word in VAGUE_WORDS) else "clear"
    revising = any(word in lowered for word in REVISION_WORDS)

    claims = []
    for keywords, claim_type, scope in CLAIM_RULES:
        if not any(keyword in lowered for keyword in keywords):
            continue
        revised = _prior_claim_id(prior, scope) if revising else None
        claims.append(
            {
                "statement": candidate_text.strip(),
                "claim_type": claim_type,
                "scope": scope,
                "clarity": clarity,
                "revises_claim_id": revised,
            }
        )

    diagnoses = {claim["scope"] for claim in claims if claim["claim_type"] == "diagnosis"}
    released = any(claim["claim_type"] == "release_decision" for claim in claims)
    return {
        "claims": claims,
        "covered": {
            "initial_explanation": bool(diagnoses),
            "release_decision": released,
            "cross_company": "cross_company" in diagnoses,
            "revocation": "revocation" in diagnoses,
            "final_recommendation": released and stage == "release_discussion",
        },
        "contradiction_note": None,
    }


def _prior_claim_id(prior: list[dict], scope: str) -> str | None:
    for claim in reversed(prior):
        if claim.get("scope") == scope:
            return claim.get("id")
    return None


def _passing_check_ids(runs: list[dict]) -> set[str]:
    return {
        result["check_id"]
        for run in runs
        for result in (run.get("results") or [])
        if result.get("passed")
    }


def _observation_level(evidence: DimensionEvidence, passing: set[str], claims: list[dict]) -> str:
    if evidence.check_id and evidence.check_id in passing:
        return "demonstrated"
    related = any(
        claim.get("scope") in evidence.scopes or claim.get("claim_type") in evidence.claim_types
        for claim in claims
    )
    return "partly_demonstrated" if related else "not_observed"


def _entry(dimension: str, title: str, level: str, refs: list[dict], assistance: str) -> dict:
    cited = ", ".join(f"{ref['type']} {ref['id']}" for ref in refs) or "no records"
    return {
        "dimension": dimension,
        "title": title,
        "observation_level": level,
        "explanation": f"Scripted assessment of {dimension}: {level}, from {cited}.",
        "supporting_refs": refs,
        "opposing_refs": [],
        "assistance": assistance,
        "uncertainty": "A recorded pass covers the recorded conditions only.",
        "follow_up": "Ask how they would check cached access after a permission change.",
    }


def scripted_assessment(system: str) -> dict:
    """The double's assessment: fixed dimensions over the ids in the record block."""
    record = prompts.read_json_block(system, prompts.BLOCK_RECORD, default={}) or {}
    segments = record.get("segments") or []
    completed = [run for run in (record.get("runs") or []) if run.get("status") == "completed"]
    claims = record.get("claims") or []
    hints = record.get("hint_segment_ids") or []

    refs: list[dict] = []
    if segments:
        refs.append({"type": "segment", "id": segments[0]["id"]})
    refs.extend({"type": "run", "id": run["id"]} for run in completed)
    if claims:
        refs.append({"type": "claim", "id": claims[0]["id"]})
    if INVALID_REFS_MARKER in system:
        refs = [{"type": "segment", "id": "seg_nope"}]

    passing = _passing_check_ids(completed)
    assistance = (
        f"Hints were recorded in segments {', '.join(hints)}."
        if hints
        else "No assistance was recorded."
    )
    dimensions = [
        _entry(
            dimension,
            DIMENSION_EVIDENCE[dimension].title,
            _observation_level(DIMENSION_EVIDENCE[dimension], passing, claims),
            list(refs),
            assistance,
        )
        for dimension in prompts.DIMENSIONS
    ]
    findings = [
        _entry(
            dimension,
            title,
            _observation_level(DIMENSION_EVIDENCE[dimension], passing, claims),
            list(refs),
            assistance,
        )
        for dimension, title in EXPANDED_FINDINGS
    ]
    return {
        "summary": (
            f"Scripted assessment over {len(segments)} segments, {len(completed)} completed "
            f"runs, and {len(claims)} claims."
        ),
        "dimensions": dimensions,
        "findings": findings,
    }


class ScriptedLLM:
    """Deterministic stand-in for a model. Test and offline-demo use only."""

    model_id = "scripted-test-double"

    async def stream_text(
        self, messages: list[dict], *, temperature: float = 0.4, max_tokens: int = 220
    ) -> AsyncIterator[str]:
        system = _require_task(messages, prompts.TASK_SPOKEN_TURN)
        words = scripted_spoken_turn(system).split(" ")
        for index, word in enumerate(words):
            yield word if index == 0 else f" {word}"

    async def complete_json(self, messages: list[dict], *, max_tokens: int = 1500) -> dict:
        task = prompts.read_task(messages)
        if task == prompts.TASK_CLAIMS:
            return scripted_claims(_system_text(messages), _user_text(messages))
        if task == prompts.TASK_ASSESSMENT:
            return scripted_assessment(_system_text(messages))
        raise LLMError(f"the scripted double has no JSON answer for a {task!r} prompt")


def build_llm(settings: Settings) -> LLMClient:
    """The client named by `LLM_PROVIDER`, or a RuntimeError naming what is missing."""
    if settings.LLM_PROVIDER == "scripted":
        return ScriptedLLM()
    if settings.LLM_PROVIDER != "openai":
        raise RuntimeError(
            f"LLM_PROVIDER must be 'openai' or 'scripted', not {settings.LLM_PROVIDER!r}"
        )
    if not settings.LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY is required when LLM_PROVIDER is 'openai'")
    if not settings.LLM_MODEL:
        raise RuntimeError("LLM_MODEL is required when LLM_PROVIDER is 'openai'")
    return OpenAICompatibleClient(
        base_url=settings.LLM_BASE_URL, api_key=settings.LLM_API_KEY, model=settings.LLM_MODEL
    )
