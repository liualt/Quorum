"""The voice service and the `/start` wiring that uses it.

Nothing here reaches Agora. The service is built with credentials shaped the way
Agora demands but signed by nobody, so the token minting and the wire config are
exercised locally, and a fake session stands in wherever a real one would speak
to the network.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.interview import prompts
from app.interview.agora import (
    AgoraVoiceService,
    JoinData,
    NullVoiceService,
    _open_session,
    build_voice,
)
from app.main import create_app
from app.routes.deps import llm_token
from app.routes.interviews import start_interview
from app.storage import repo
from tests.conftest import ORIGIN, create_interview, seed_interview

# Agora refuses any credential that is not exactly 32 characters, dummy or not.
APP_ID = "a" * 32
APP_CERTIFICATE = "c" * 32

PUBLIC_BASE_URL = "https://quorum.example"
LLM_SECRET = "llm-secret"


def agora_settings(**overrides) -> Settings:
    return Settings(
        **{
            "AGORA_APP_ID": APP_ID,
            "AGORA_APP_CERTIFICATE": APP_CERTIFICATE,
            "CUSTOM_LLM_PUBLIC_BASE_URL": PUBLIC_BASE_URL,
            "CUSTOM_LLM_AUTH_SECRET": LLM_SECRET,
            **overrides,
        }
    )


class FakeSession:
    """Stands in for an `AsyncAgentSession`; records what was asked of it."""

    def __init__(self, agent_id: str = "agent-abc"):
        self.agent_id = agent_id
        self.calls: list[tuple] = []
        # What a session whose agent has already hung up does to every call.
        self.fails = False

    def _record(self, call: tuple) -> None:
        self.calls.append(call)
        if self.fails:
            raise RuntimeError("Cannot speak in stopped state")

    async def start(self) -> str:
        self._record(("start",))
        return self.agent_id

    async def stop(self) -> None:
        self._record(("stop",))

    async def say(self, text, priority=None, interruptable=None) -> None:
        self._record(("say", text, priority, interruptable))

    async def interrupt(self) -> None:
        self._record(("interrupt",))


class FakeAgents:
    """The `client.agents` namespace, with one canned answer about one agent."""

    def __init__(self, *, status: str = "RUNNING", fails: bool = False):
        self.status = status
        self.fails = fails
        self.asked: list[str] = []

    async def get(self, appid: str, agent_id: str):
        self.asked.append(agent_id)
        if self.fails:
            raise RuntimeError("agora is unreachable")
        return SimpleNamespace(agent_id=agent_id, status=self.status)


class FakeClient:
    """Stands in for `AsyncAgora`; records the agents it was asked to stop."""

    def __init__(self, *, fails: bool = False, status: str = "RUNNING", blind: bool = False):
        self.fails = fails
        self.stopped: list[str] = []
        self.agents = FakeAgents(status=status, fails=blind)

    async def stop_agent(self, agent_id: str) -> None:
        self.stopped.append(agent_id)
        if self.fails:
            raise RuntimeError("agora is unreachable")


def fake_voice(session: FakeSession | None = None, client=None) -> AgoraVoiceService:
    """A service with neither a real session nor a real client behind it."""
    session = session or FakeSession()
    return AgoraVoiceService(
        agora_settings(),
        client=client or FakeClient(),
        session_factory=lambda agent, join: session,
    )


def start_kwargs(**overrides) -> dict:
    return {
        "llm_url": f"{PUBLIC_BASE_URL}/llm/itv_1/chat/completions",
        "llm_token": "bearer-token",
        "greeting": "Hello Ada, you are speaking with three AI interviewers.",
        "instructions": "You are the panel.",
        **overrides,
    }


# --- build_voice ----------------------------------------------------------

def test_build_voice_is_null_without_agora_credentials(settings):
    assert isinstance(build_voice(settings), NullVoiceService)


def test_build_voice_is_null_without_a_public_url_for_the_model_endpoint():
    settings = agora_settings(CUSTOM_LLM_PUBLIC_BASE_URL="")

    assert isinstance(build_voice(settings), NullVoiceService)


def test_build_voice_is_agora_when_both_ends_are_configured():
    assert isinstance(build_voice(agora_settings()), AgoraVoiceService)


def test_the_null_service_is_disabled_and_joins_nothing():
    voice = NullVoiceService()

    assert voice.enabled is False
    assert voice.make_join("itv_1") == JoinData(enabled=False)


# --- join data ------------------------------------------------------------

def test_make_join_mints_a_channel_and_token_for_the_interview():
    join = fake_voice().make_join("itv_1")

    assert join.enabled is True
    assert join.app_id == APP_ID
    assert join.channel == "quorum-itv_1"
    assert join.token.startswith("007")
    assert len(join.token) > 100
    # The candidate and the agent are two different publishers in one channel.
    assert 1_000 <= join.uid <= 9_999_999
    assert 10_000_000 <= join.agent_uid <= 99_999_999
    assert join.agent_id == ""


# --- the wire config ------------------------------------------------------

def test_build_properties_points_the_agent_at_this_backend():
    voice = AgoraVoiceService(agora_settings())
    join = voice.make_join("itv_1")

    properties = voice.build_properties(join, **start_kwargs())

    assert properties["channel"] == "quorum-itv_1"
    assert properties["agent_rtc_uid"] == str(join.agent_uid)
    assert properties["remote_rtc_uids"] == [str(join.uid)]
    assert properties["enable_string_uid"] is False
    assert properties["idle_timeout"] == 120
    assert properties["llm"]["url"] == f"{PUBLIC_BASE_URL}/llm/itv_1/chat/completions"
    assert properties["llm"]["api_key"] == "bearer-token"
    assert properties["llm"]["vendor"] == "custom"
    assert properties["llm"]["max_history"] == 8
    assert properties["llm"]["params"] == {
        "model": "quorum-controller",
        "max_tokens": 220,
        "temperature": 0.4,
    }
    assert properties["advanced_features"]["enable_rtm"] is True
    assert properties["parameters"]["data_channel"] == "rtm"
    assert properties["interruption"]["enable"] is True


def test_build_properties_carries_the_managed_speech_vendors():
    settings = agora_settings()
    voice = AgoraVoiceService(settings)

    properties = voice.build_properties(voice.make_join("itv_1"), **start_kwargs())

    assert properties["asr"]["vendor"] == "deepgram"
    assert properties["asr"]["params"]["model"] == settings.AGORA_ASR_MODEL == "nova-3"
    assert properties["tts"]["vendor"] == "minimax"
    assert properties["tts"]["params"]["voice_setting"] == {
        "voice_id": settings.AGORA_TTS_VOICE_ID
    }
    # Neither carries a key of ours: both run on Agora-managed credentials, and
    # the model name travels as the preset hint the SDK folds into the request.
    assert "key" not in properties["tts"]["params"]
    assert properties["tts"]["_minimax_preset_model"] == settings.AGORA_TTS_MODEL


def test_build_properties_keeps_the_tuned_turn_detection():
    voice = AgoraVoiceService(agora_settings())

    turn_detection = voice.build_properties(
        voice.make_join("itv_1"), **start_kwargs()
    )["turn_detection"]

    assert turn_detection["config"]["speech_threshold"] == 0.5
    assert turn_detection["config"]["start_of_speech"] == {
        "mode": "vad",
        "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300},
    }
    assert turn_detection["config"]["end_of_speech"] == {
        "mode": "vad",
        "vad_config": {"silence_duration_ms": 480},
    }


def test_build_properties_makes_agora_speak_the_opening_line():
    """The endpoint rejects an empty transcript, so the greeting is Agora's job."""
    voice = AgoraVoiceService(agora_settings())
    kwargs = start_kwargs()

    properties = voice.build_properties(voice.make_join("itv_1"), **kwargs)

    assert properties["llm"]["greeting_message"] == kwargs["greeting"]
    assert properties["llm"]["system_messages"] == [
        {"role": "system", "content": kwargs["instructions"]}
    ]


# --- the session ----------------------------------------------------------

async def test_start_agent_returns_the_agent_id_and_keeps_the_session():
    session = FakeSession()
    voice = fake_voice(session)

    agent_id = await voice.start_agent(voice.make_join("itv_1"), **start_kwargs())

    assert agent_id == "agent-abc"
    assert session.calls == [("start",)]


async def test_say_appends_by_default_and_interrupts_when_asked():
    session = FakeSession()
    voice = fake_voice(session)
    agent_id = await voice.start_agent(voice.make_join("itv_1"), **start_kwargs())

    await voice.say(agent_id, "One more thing.")
    await voice.say(agent_id, "Hold on.", interrupt=True)

    assert session.calls[1:] == [
        ("say", "One more thing.", "APPEND", True),
        ("say", "Hold on.", "INTERRUPT", True),
    ]


async def test_interrupt_stops_the_agent_mid_sentence():
    session = FakeSession()
    voice = fake_voice(session)
    agent_id = await voice.start_agent(voice.make_join("itv_1"), **start_kwargs())

    await voice.interrupt(agent_id)

    assert session.calls[1:] == [("interrupt",)]


async def test_a_session_that_stops_answering_is_dropped_not_raised(caplog):
    """After Agora's idle timeout the session raises; the controller says inline."""
    session = FakeSession()
    voice = fake_voice(session)
    agent_id = await voice.start_agent(voice.make_join("itv_1"), **start_kwargs())
    session.fails = True

    with caplog.at_level("WARNING"):
        await voice.say(agent_id, "Still there?")
        await voice.interrupt(agent_id)

    # The first call dropped the session; the second found nothing to call.
    assert session.calls[1:] == [("say", "Still there?", "APPEND", True)]
    assert [record.levelname for record in caplog.records] == ["WARNING", "WARNING"]
    assert "no longer live" in caplog.records[0].message
    assert "not held by this process" in caplog.records[1].message


async def test_speaking_to_an_unknown_agent_is_a_warning_not_a_failure(caplog):
    voice = fake_voice()

    with caplog.at_level("WARNING"):
        await voice.say("agent-from-a-previous-process", "Hello?")
        await voice.interrupt("agent-from-a-previous-process")

    assert len(caplog.records) == 2
    assert "agent-from-a-previous-process" in caplog.text


def test_every_attempt_asks_for_its_own_agent_name():
    """Agora refuses a name it has already seen, so a retry cannot reuse one."""
    sessions = []

    def remember(agent, join):
        sessions.append(_open_session(agent, join))
        return sessions[-1]

    voice = AgoraVoiceService(
        agora_settings(), client=FakeClient(), session_factory=remember
    )
    join = voice.make_join("itv_1")

    voice.build_properties(join, **start_kwargs())
    voice.build_properties(join, **start_kwargs())

    names = [session._name for session in sessions]
    assert all(name.startswith("quorum-itv_1-") for name in names)
    assert names[0] != names[1]


@pytest.mark.parametrize(
    ("status", "live"),
    [
        ("RUNNING", True),
        ("STARTING", True),
        ("STOPPED", False),
        ("FAILED", False),
        ("IDLE", False),
    ],
)
async def test_agent_is_live_follows_the_status_agora_reports(status, live):
    client = FakeClient(status=status)

    assert await fake_voice(client=client).agent_is_live("agent-abc") is live
    assert client.agents.asked == ["agent-abc"]


async def test_an_agent_agora_will_not_talk_about_is_not_live(caplog):
    """Unreachable, unknown, refused: none of them is an agent worth rejoining."""
    with caplog.at_level("WARNING"):
        assert await fake_voice(client=FakeClient(blind=True)).agent_is_live("gone") is False

    assert "could not read the state of voice agent gone" in caplog.text


async def test_stop_agent_stops_the_session_it_started():
    session = FakeSession()
    client = FakeClient()
    voice = fake_voice(session, client=client)
    agent_id = await voice.start_agent(voice.make_join("itv_1"), **start_kwargs())

    await voice.stop_agent(agent_id)

    assert session.calls[1:] == [("stop",)]
    assert client.stopped == []


async def test_stop_agent_asks_agora_directly_for_an_agent_it_does_not_hold():
    client = FakeClient(fails=True)

    await fake_voice(client=client).stop_agent("agent-from-a-previous-process")

    # The call was made, and the failure it raised did not escape.
    assert client.stopped == ["agent-from-a-previous-process"]


# --- /start and DELETE ----------------------------------------------------

class StubVoice:
    """A voice service with an Agora-shaped answer and no Agora behind it."""

    enabled = True

    def __init__(self, *, fails: bool = False, fails_join: bool = False, live: bool = True):
        self.fails = fails
        self.fails_join = fails_join
        self.live = live
        self.agent_id = "agent-abc"
        self.joins: list[dict] = []
        self.started: list[dict] = []
        self.stopped: list[str] = []
        self.asked: list[str] = []

    async def agent_is_live(self, agent_id: str) -> bool:
        self.asked.append(agent_id)
        return self.live

    def make_join(self, interview_id, *, uid=None, agent_uid=None, agent_id="") -> JoinData:
        self.joins.append({"uid": uid, "agent_uid": agent_uid, "agent_id": agent_id})
        if self.fails_join:
            raise ValueError("app_id must be exactly 32 characters")
        return JoinData(
            enabled=True,
            app_id=APP_ID,
            channel=f"quorum-{interview_id}",
            uid=uid or 4242,
            # A token is minted per join, so a rejoin is visibly a fresh one.
            token=f"join-token-{len(self.joins)}",
            agent_uid=agent_uid or 99887766,
            agent_id=agent_id,
        )

    async def start_agent(self, join, *, llm_url, llm_token, greeting, instructions) -> str:
        # A real start does I/O here; yielding lets a racing start run.
        await asyncio.sleep(0)
        if self.fails:
            raise RuntimeError("agora refused the agent")
        self.started.append(
            {
                "channel": join.channel,
                "llm_url": llm_url,
                "llm_token": llm_token,
                "greeting": greeting,
                "instructions": instructions,
            }
        )
        return self.agent_id

    async def stop_agent(self, agent_id: str) -> None:
        self.stopped.append(agent_id)

    async def say(self, agent_id, text, *, interrupt=False) -> None:
        return None

    async def interrupt(self, agent_id) -> None:
        return None


def reachable(settings: Settings) -> Settings:
    """Settings a voice agent could call back into, with voice left injectable."""
    return settings.model_copy(
        update={
            "CUSTOM_LLM_PUBLIC_BASE_URL": PUBLIC_BASE_URL,
            "CUSTOM_LLM_AUTH_SECRET": LLM_SECRET,
        }
    )


@pytest.fixture
def voice_client(settings):
    with TestClient(create_app(reachable(settings)), raise_server_exceptions=True) as client:
        yield client


def segments(app, interview_id):
    return repo.list_segments(app.state.db, interview_id)


def test_start_greets_the_candidate_in_the_transcript_even_without_voice(client, app, candidate):
    response = client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)

    assert response.status_code == 200
    assert response.json() == {"voice": {"enabled": False}}

    greeting = segments(app, candidate["id"])[0]
    assert greeting["speaker"] == "technical"
    assert greeting["kind"] == "greeting"
    assert greeting["status"] == "complete"
    assert greeting["stage"] == "briefing"
    assert greeting["generation"] == 0
    assert "AI" in greeting["text"]
    assert greeting["text"] == prompts.greeting_text("Ada Lovelace")


def test_starting_twice_does_not_greet_twice(client, app, candidate):
    client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)
    client.post(f"/api/interviews/{candidate['id']}/start", headers=ORIGIN)

    kinds = [segment["kind"] for segment in segments(app, candidate["id"])]
    assert kinds == ["greeting"]


def test_start_launches_the_agent_and_reports_the_channel(voice_client):
    app = voice_client.app
    voice = StubVoice()
    app.state.voice = voice
    interview = create_interview(voice_client)

    response = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    assert response.status_code == 200
    assert response.json()["voice"] == {
        "enabled": True,
        "app_id": APP_ID,
        "channel": f"quorum-{interview['id']}",
        "uid": 4242,
        "token": "join-token-1",
        "agent_uid": 99887766,
        "agent_id": "agent-abc",
    }

    row = repo.get_interview(app.state.db, interview["id"])
    assert row["status"] == "live"
    assert row["voice_status"] == "connecting"
    assert row["agora_channel"] == f"quorum-{interview['id']}"
    assert row["agora_agent_id"] == "agent-abc"
    assert row["agora_uid"] == 4242
    assert row["agora_agent_uid"] == 99887766

    assert voice.started == [
        {
            "channel": f"quorum-{interview['id']}",
            "llm_url": f"{PUBLIC_BASE_URL}/llm/{interview['id']}/chat/completions",
            "llm_token": llm_token(app.state.settings, interview["id"]),
            "greeting": prompts.greeting_text("Ada Lovelace"),
            "instructions": prompts.agent_instructions(),
        }
    ]


def test_starting_again_rejoins_an_agent_that_is_still_live(voice_client):
    voice = StubVoice()
    voice_client.app.state.voice = voice
    interview = create_interview(voice_client)

    voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)
    again = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    # One agent, joined twice: the reload got a fresh token for the identities
    # the agent is already listening to, and nothing was started or stopped.
    assert voice.asked == ["agent-abc"]
    assert len(voice.started) == 1
    assert voice.stopped == []
    assert voice.joins[1] == {"uid": 4242, "agent_uid": 99887766, "agent_id": "agent-abc"}
    assert again.json()["voice"]["token"] == "join-token-2"
    assert again.json()["voice"]["agent_id"] == "agent-abc"


def test_starting_again_replaces_an_agent_that_has_hung_up(voice_client):
    """An id on the row outlives the agent: one left alone idles out after 120s."""
    app = voice_client.app
    voice = StubVoice()
    app.state.voice = voice
    interview = create_interview(voice_client)
    voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    voice.live = False
    voice.agent_id = "agent-second"
    again = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    # The dead one was stopped and a new one took the channel, rather than the
    # candidate being handed a valid token for an agent that cannot speak.
    assert voice.stopped == ["agent-abc"]
    assert len(voice.started) == 2
    assert again.json()["voice"]["agent_id"] == "agent-second"
    assert repo.get_interview(app.state.db, interview["id"])["agora_agent_id"] == "agent-second"


def test_start_falls_back_to_text_when_the_agent_will_not_start(voice_client):
    app = voice_client.app
    app.state.voice = StubVoice(fails=True)
    interview = create_interview(voice_client)

    response = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    assert response.status_code == 200
    body = response.json()["voice"]
    assert body["enabled"] is False
    assert body["reason"]

    row = repo.get_interview(app.state.db, interview["id"])
    assert row["status"] == "live"
    assert row["voice_status"] == "disconnected"
    assert row["agora_agent_id"] is None
    # The interview still opens with the disclosure, spoken or not.
    assert segments(app, interview["id"])[0]["kind"] == "greeting"


def test_a_malformed_agora_credential_leaves_the_interview_in_text_mode(voice_client):
    """`make_join` raises on a credential Agora would reject; `/start` must not."""
    app = voice_client.app
    app.state.voice = AgoraVoiceService(
        agora_settings(AGORA_APP_ID="a" * 31), client=FakeClient()
    )
    interview = create_interview(voice_client)

    response = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    assert response.status_code == 200
    assert response.json()["voice"] == {
        "enabled": False,
        "reason": "the voice agent could not be reached",
    }
    row = repo.get_interview(app.state.db, interview["id"])
    assert row["status"] == "live"
    assert row["voice_status"] == "disconnected"
    assert segments(app, interview["id"])[0]["kind"] == "greeting"


def test_a_failed_rejoin_keeps_the_agent_id_for_finish(voice_client):
    app = voice_client.app
    voice = StubVoice()
    app.state.voice = voice
    interview = create_interview(voice_client)
    voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    voice.fails_join = True
    response = voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    assert response.json()["voice"]["enabled"] is False
    row = repo.get_interview(app.state.db, interview["id"])
    assert row["voice_status"] == "disconnected"
    # The agent is still in the channel; whoever finishes has to stop it.
    assert row["agora_agent_id"] == "agent-abc"


def test_the_start_failure_log_never_quotes_the_rejected_input(voice_client, caplog):
    """A pydantic error embeds `input_value=`, and the input carries the bearer."""
    voice_client.app.state.voice = AgoraVoiceService(
        agora_settings(AGORA_APP_ID="a" * 31), client=FakeClient()
    )
    interview = create_interview(voice_client)

    with caplog.at_level("ERROR"):
        voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    assert [record.getMessage() for record in caplog.records] == [
        f"voice is unavailable for {interview['id']}: ValueError"
    ]
    # The class name, never the message: that is where a rejected input is quoted.
    assert "a" * 31 not in caplog.text


@pytest.fixture
async def live_voice_app(settings):
    """The reachable app with its lifespan on the test's own loop.

    `TestClient` serializes requests on one portal thread, so two starts can only
    be raced by driving the route directly.
    """
    app = create_app(reachable(settings))
    async with app.router.lifespan_context(app):
        yield app


async def test_two_starts_at_once_leave_one_agent_and_one_greeting(live_voice_app):
    app = live_voice_app
    voice = StubVoice()
    app.state.voice = voice
    row = seed_interview(app)
    # Both requests resolved their dependency before either body ran, so both
    # carry the same row: the one that says there is no agent yet.
    request = SimpleNamespace(app=app)

    await asyncio.gather(
        start_interview(row["id"], request, row),
        start_interview(row["id"], request, row),
    )

    assert len(voice.started) == 1
    assert [segment["kind"] for segment in segments(app, row["id"])] == ["greeting"]
    assert repo.get_interview(app.state.db, row["id"])["agora_agent_id"] == "agent-abc"


def test_deleting_an_interview_stops_its_agent(voice_client):
    app = voice_client.app
    voice = StubVoice()
    app.state.voice = voice
    interview = create_interview(voice_client)
    voice_client.post(f"/api/interviews/{interview['id']}/start", headers=ORIGIN)

    response = voice_client.delete(f"/api/interviews/{interview['id']}", headers=ORIGIN)

    assert response.status_code == 204
    assert voice.stopped == ["agent-abc"]


def test_deleting_a_text_interview_stops_nothing(voice_client):
    voice = StubVoice()
    voice_client.app.state.voice = voice
    interview = create_interview(voice_client)

    voice_client.delete(f"/api/interviews/{interview['id']}", headers=ORIGIN)

    assert voice.stopped == []


def test_health_reports_the_service_that_was_built(voice_client):
    voice_client.app.state.voice = StubVoice()

    assert voice_client.get("/api/health").json()["voice_enabled"] is True
