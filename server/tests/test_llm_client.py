"""The OpenAI-compatible client against a fake server, and the scripted double.

The scripted double is fed prompts built by `app.interview.prompts`, because the
blocks it parses are the contract between the two modules.
"""

import json

import httpx2
import pytest

from app.config import Settings
from app.interview import prompts
from app.interview.llm_client import (
    LLMError,
    OpenAICompatibleClient,
    ScriptedLLM,
    build_llm,
)
from tests.test_prompts import RECORD, RUBRIC, RUN, SEGMENTS, turn_context

CHUNK = (
    'data: {{"id":"x","object":"chat.completion.chunk","choices":'
    '[{{"index":0,"delta":{{"content":"{content}"}},"finish_reason":null}}]}}\n\n'
)
SSE_BODY = CHUNK.format(content="Hello") + CHUNK.format(content=" there") + "data: [DONE]\n\n"

MESSAGES = [{"role": "system", "content": "# quorum-task: spoken_turn"},
            {"role": "user", "content": "hello"}]


class TrackingStream(httpx2.AsyncByteStream):
    """An SSE body that records whether the response was closed."""

    def __init__(self):
        self.closed = False

    async def __aiter__(self):
        for line in SSE_BODY.splitlines(keepends=True):
            yield line.encode()

    async def aclose(self):
        self.closed = True


def json_body(content: str) -> dict:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                     "finish_reason": "stop"}],
    }


@pytest.fixture
async def fake_openai():
    """Builds `OpenAICompatibleClient`s whose transport is a handler you supply."""
    http_clients = []

    def build(handler, *, model="test-model"):
        http = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
        http_clients.append(http)
        return OpenAICompatibleClient(
            base_url="http://fake.invalid/v1", api_key="key", model=model, http_client=http
        )

    yield build

    for http in http_clients:
        await http.aclose()


@pytest.fixture
def requests():
    return []


@pytest.fixture
def recording_handler(requests):
    def handler(request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content.decode())
        requests.append(body)
        if body.get("stream"):
            return httpx2.Response(
                200, content=SSE_BODY.encode(), headers={"content-type": "text/event-stream"}
            )
        return httpx2.Response(200, json=json_body('{"claims": [], "ok": true}'))

    return handler


# --- OpenAICompatibleClient -------------------------------------------------------


async def test_stream_text_yields_each_delta_in_order(fake_openai, recording_handler, requests):
    client = fake_openai(recording_handler)

    chunks = [chunk async for chunk in client.stream_text(MESSAGES, temperature=0.2, max_tokens=90)]

    assert chunks == ["Hello", " there"]
    assert requests[0]["stream"] is True
    assert requests[0]["model"] == "test-model"
    assert requests[0]["temperature"] == 0.2
    assert requests[0]["max_tokens"] == 90
    assert requests[0]["messages"] == MESSAGES


async def test_stream_text_closes_the_stream_when_the_caller_stops_early(fake_openai):
    """An interrupted turn abandons the generator; the connection must be released."""
    bodies = []

    def handler(request):
        body = TrackingStream()
        bodies.append(body)
        return httpx2.Response(
            200, stream=body, headers={"content-type": "text/event-stream"}
        )

    chunks = fake_openai(handler).stream_text(MESSAGES)
    first = await anext(chunks)

    assert first == "Hello"
    assert bodies[0].closed is False

    await chunks.aclose()

    assert bodies[0].closed is True


async def test_complete_json_parses_the_body_and_asks_for_json_mode(
    fake_openai, recording_handler, requests
):
    client = fake_openai(recording_handler)

    payload = await client.complete_json(MESSAGES, max_tokens=400)

    assert payload == {"claims": [], "ok": True}
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["max_tokens"] == 400
    assert "stream" not in requests[0] or requests[0]["stream"] is False


async def test_the_model_id_is_the_configured_model(fake_openai, recording_handler):
    assert fake_openai(recording_handler, model="gpt-x").model_id == "gpt-x"


async def test_a_server_error_while_streaming_raises_llm_error(fake_openai):
    def handler(request):
        return httpx2.Response(500, json={"error": {"message": "boom"}})

    client = fake_openai(handler)

    with pytest.raises(LLMError):
        [chunk async for chunk in client.stream_text(MESSAGES)]


async def test_a_server_error_on_json_raises_llm_error(fake_openai):
    def handler(request):
        return httpx2.Response(500, json={"error": {"message": "boom"}})

    with pytest.raises(LLMError):
        await fake_openai(handler).complete_json(MESSAGES)


async def test_a_transport_error_raises_llm_error(fake_openai):
    def handler(request):
        raise httpx2.ConnectError("no route")

    with pytest.raises(LLMError):
        await fake_openai(handler).complete_json(MESSAGES)


async def test_a_non_json_completion_raises_llm_error(fake_openai):
    def handler(request):
        return httpx2.Response(200, json=json_body("not json at all"))

    with pytest.raises(LLMError):
        await fake_openai(handler).complete_json(MESSAGES)


async def test_an_empty_completion_raises_llm_error(fake_openai):
    def handler(request):
        return httpx2.Response(200, json=json_body(None))

    with pytest.raises(LLMError):
        await fake_openai(handler).complete_json(MESSAGES)


# --- build_llm --------------------------------------------------------------------


def test_build_llm_returns_the_scripted_double(settings):
    client = build_llm(settings)

    assert isinstance(client, ScriptedLLM)
    assert client.model_id == "scripted-test-double"


def test_build_llm_requires_an_api_key_for_openai():
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        build_llm(Settings(LLM_PROVIDER="openai", LLM_API_KEY="", LLM_MODEL="gpt-x"))


def test_build_llm_requires_a_model_for_openai():
    with pytest.raises(RuntimeError, match="LLM_MODEL"):
        build_llm(Settings(LLM_PROVIDER="openai", LLM_API_KEY="k", LLM_MODEL=""))


def test_build_llm_builds_the_openai_client_when_configured():
    client = build_llm(Settings(LLM_PROVIDER="openai", LLM_API_KEY="k", LLM_MODEL="gpt-x"))

    assert isinstance(client, OpenAICompatibleClient)
    assert client.model_id == "gpt-x"


def test_build_llm_rejects_an_unknown_provider():
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        build_llm(Settings(LLM_PROVIDER="carrier-pigeon"))


# --- ScriptedLLM: spoken turns ----------------------------------------------------


async def spoken(**overrides) -> str:
    messages = prompts.spoken_turn_messages(turn_context(**overrides))
    return "".join([chunk async for chunk in ScriptedLLM().stream_text(messages)])


async def test_scripted_spoken_turn_names_the_role_and_the_instruction_kind():
    text = await spoken(role="product", instruction_kind="probe_deeper", pending_runs=[])

    assert "Product manager" in text
    assert "probe_deeper" in text


async def test_scripted_spoken_turn_cites_the_pending_run_and_its_failed_checks():
    text = await spoken()

    assert "your latest run" in text
    assert "cross_company_isolation" in text
    assert "repeat_search_efficiency" in text


async def test_scripted_spoken_turn_does_not_narrate_a_pass_for_a_run_that_timed_out():
    """A timed-out run has no results, so "it passed every check" would be a lie."""
    timed_out = dict(RUN, status="timeout", results=[])
    text = await spoken(pending_runs=[timed_out])

    assert "did not complete" in text
    assert "passed" not in text


async def test_scripted_spoken_turn_says_a_pending_run_passed_everything():
    passing = dict(RUN, results=[{"check_id": "access_filtering", "passed": True, "steps": [],
                                 "search_calls": None, "max_search_calls": None,
                                 "efficiency_ok": None, "error": None}])
    text = await spoken(pending_runs=[passing])

    assert "your latest run" in text
    assert "access_filtering" in text


async def test_scripted_spoken_turn_omits_run_talk_without_a_pending_run():
    text = await spoken(pending_runs=[])

    assert "your latest run" not in text


async def test_scripted_scenario_notice_is_the_fixed_sentence():
    text = await spoken(role="customer", instruction_kind="scenario_notice")

    assert text == (
        "Customer administrator here. I just removed an employee's access to a document. "
        "Can they still retrieve it from a search they ran earlier?"
    )


async def test_scripted_hint_starts_with_the_narrower_question_phrase():
    text = await spoken(instruction_kind="hint")

    assert text.startswith("Here is a narrower question:")
    assert "Technical interviewer" in text


async def test_scripted_spoken_turn_is_chunked_by_words():
    messages = prompts.spoken_turn_messages(turn_context())
    chunks = [chunk async for chunk in ScriptedLLM().stream_text(messages)]

    assert len(chunks) > 3
    assert all(chunk.strip().count(" ") == 0 for chunk in chunks)
    assert "".join(chunks) == await spoken()


async def test_scripted_stream_rejects_a_non_spoken_prompt():
    messages = prompts.claims_messages(SEGMENTS[1], SEGMENTS, [], [])

    with pytest.raises(LLMError):
        [chunk async for chunk in ScriptedLLM().stream_text(messages)]


# --- ScriptedLLM: claims ----------------------------------------------------------


async def claims(text, *, prior=None, stage="investigation", runs=()):
    segment = dict(SEGMENTS[1], text=text, stage=stage)
    messages = prompts.claims_messages(segment, [segment], list(prior or []), list(runs))
    return await ScriptedLLM().complete_json(messages)


async def test_scripted_claims_reads_a_cross_company_diagnosis():
    payload = await claims("The cache is keyed by the query only, so it can leak to another company.")

    assert payload["claims"][0]["claim_type"] == "diagnosis"
    assert payload["claims"][0]["scope"] == "cross_company"
    assert payload["claims"][0]["clarity"] == "clear"
    assert payload["claims"][0]["revises_claim_id"] is None
    assert payload["covered"]["initial_explanation"] is True
    assert payload["covered"]["cross_company"] is True
    assert payload["covered"]["revocation"] is False
    assert payload["contradiction_note"] is None


async def test_scripted_claims_reads_a_revocation_diagnosis():
    payload = await claims("After a revoke the cached entry is stale.")
    scopes = [claim["scope"] for claim in payload["claims"]]

    assert "revocation" in scopes
    assert payload["covered"]["revocation"] is True
    assert payload["covered"]["cross_company"] is False


async def test_scripted_claims_reads_a_release_decision():
    payload = await claims("I would not ship this today.")
    kinds = [claim["claim_type"] for claim in payload["claims"]]

    assert "release_decision" in kinds
    assert [claim["scope"] for claim in payload["claims"] if claim["claim_type"] == "release_decision"] == ["general"]
    assert payload["covered"]["release_decision"] is True
    assert payload["covered"]["final_recommendation"] is False


async def test_scripted_claims_marks_a_final_recommendation_in_the_release_stage():
    payload = await claims("I would hold the release until the checks pass.", stage="release_discussion")

    assert payload["covered"]["final_recommendation"] is True


async def test_scripted_claims_reads_a_test_plan():
    payload = await claims("I would add a check that asserts the second search is filtered.")

    assert [claim["claim_type"] for claim in payload["claims"]] == ["test_plan"]


async def test_scripted_claims_marks_hedged_text_as_vague():
    payload = await claims("I think the cache key might be the problem, I am not sure.")

    assert payload["claims"]
    assert all(claim["clarity"] == "vague" for claim in payload["claims"])


async def test_scripted_claims_ignores_keywords_buried_in_other_words():
    payload = await claims("Your latest note about the threshold was helpful.")

    assert payload["claims"] == []


async def test_scripted_claims_still_matches_inflected_keywords():
    payload = await claims("The cache leaks, and an entry stays stale after a revoked grant.")
    scopes = [claim["scope"] for claim in payload["claims"]]

    assert scopes == ["cross_company", "revocation"]


async def test_scripted_claims_returns_nothing_for_small_talk():
    payload = await claims("Give me a moment to read this.")

    assert payload["claims"] == []
    assert payload["covered"] == {
        "initial_explanation": False, "release_decision": False, "cross_company": False,
        "revocation": False, "final_recommendation": False,
    }


async def test_scripted_claims_revises_a_prior_claim_with_the_same_scope():
    prior = [{"id": "clm_old", "statement": "The cache is fine.", "claim_type": "diagnosis",
              "scope": "cross_company", "stage": "initial_review", "clarity": "clear"}]
    payload = await claims("Actually the shared cache does leak across companies.", prior=prior)

    assert payload["claims"][0]["revises_claim_id"] == "clm_old"


async def test_scripted_claims_does_not_revise_a_different_scope():
    prior = [{"id": "clm_old", "statement": "Revocation is late.", "claim_type": "diagnosis",
              "scope": "revocation", "stage": "initial_review", "clarity": "clear"}]
    payload = await claims("Actually the shared cache does leak across companies.", prior=prior)

    assert payload["claims"][0]["revises_claim_id"] is None


# --- ScriptedLLM: assessment ------------------------------------------------------


async def assessment(record=None):
    return await ScriptedLLM().complete_json(prompts.assessment_messages(RUBRIC, record or RECORD))


async def test_scripted_assessment_returns_four_dimensions_in_order():
    payload = await assessment()

    assert [entry["dimension"] for entry in payload["dimensions"]] == list(prompts.DIMENSIONS)
    assert len(payload["findings"]) == 2
    assert payload["summary"]


async def test_scripted_assessment_only_references_ids_from_the_record():
    payload = await assessment()
    refs = [ref for entry in payload["dimensions"] + payload["findings"]
            for ref in entry["supporting_refs"]]

    assert refs
    assert {ref["id"] for ref in refs} <= {"seg_1", "run_1", "clm_1"}
    assert {"type": "run", "id": "run_1"} in refs


async def test_scripted_assessment_grades_from_runs_then_claims():
    levels = {entry["dimension"]: entry["observation_level"] for entry in (await assessment())["dimensions"]}

    # access_filtering passed in the record's run, cross-company failed but has a claim,
    # and nothing touches revocation. The prompt carries run digests, not raw results,
    # so the pass has to be read off `passed_checks`.
    assert levels["implementing_checking_fix"] == "demonstrated"
    assert levels["understanding_problem"] == "partly_demonstrated"
    assert levels["responding_to_new_evidence"] == "not_observed"


async def test_scripted_assessment_names_the_hint_segments_as_assistance():
    payload = await assessment()

    assert all("seg_9" in entry["assistance"] for entry in payload["dimensions"])
    assert all("no assistance" in entry["assistance"].lower()
               for entry in (await assessment(dict(RECORD, hint_segment_ids=[])))["dimensions"])


async def test_scripted_assessment_survives_an_empty_record():
    payload = await assessment({"segments": [], "runs": [], "claims": [], "snapshots": [],
                                "hint_segment_ids": []})

    assert [entry["dimension"] for entry in payload["dimensions"]] == list(prompts.DIMENSIONS)
    assert all(entry["observation_level"] == "not_observed" for entry in payload["dimensions"])
    assert all(entry["supporting_refs"] == [] for entry in payload["dimensions"])


async def test_scripted_assessment_emits_invalid_refs_on_request():
    record = dict(RECORD, segments=[dict(SEGMENTS[0], text="[[scripted:invalid-refs]]"), SEGMENTS[1]])
    payload = await assessment(record)
    refs = [ref for entry in payload["dimensions"] for ref in entry["supporting_refs"]]

    assert {"type": "segment", "id": "seg_nope"} in refs


async def test_scripted_complete_json_rejects_a_spoken_prompt():
    with pytest.raises(LLMError):
        await ScriptedLLM().complete_json(prompts.spoken_turn_messages(turn_context()))
