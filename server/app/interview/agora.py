"""The voice side of an interview: an Agora Conversational AI agent, or nothing.

Everything that knows the Agora SDK lives in this module. The rest of the
backend sees a `VoiceService`: it asks for a channel the candidate can join,
asks for an agent to join it, and can make the panel speak or stop mid-sentence.
The agent's brain is this backend — Agora calls `/llm/{id}/chat/completions` for
every candidate turn — so a deployment the agent cannot reach has no voice, and
`build_voice` hands back the null service and the interview runs as text.
"""

import logging
import random
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from agora_agent import Area, AsyncAgora
from agora_agent.agentkit import Agent
from agora_agent.agentkit.token import generate_convo_ai_token
from agora_agent.agentkit.vendors import CustomLLM, DeepgramSTT, MiniMaxTTS

from app.config import Settings

logger = logging.getLogger(__name__)

#: The model name the agent asks for. `MODEL_NAME` in `app/routes/llm.py` is the
#: same string from the other end of the wire: what the endpoint answers as.
CONTROLLER_MODEL = "quorum-controller"

#: An agent left alone in a channel this long hangs up by itself, so a browser
#: that closed without a `/finish` cannot leave one running.
IDLE_TIMEOUT_SECONDS = 120
#: Join credentials last one session, not the SDK's default day.
TOKEN_TTL_SECONDS = 3600
#: Said aloud when the model endpoint fails, in place of the turn it owed.
FAILURE_MESSAGE = "One moment."
#: Turns of conversation Agora replays to the endpoint; the controller keeps the
#: real record, so this is only enough context for the agent to sound continuous.
MAX_HISTORY = 8
#: Spoken turns are short by design — a panel that lectures stops being an
#: interview — and a cap is the cheapest way to enforce it.
MAX_SPOKEN_TOKENS = 220
SPOKEN_TEMPERATURE = 0.4

#: Voice-activity thresholds tuned for a candidate who thinks out loud: long
#: enough at the end of a phrase not to talk over a pause, short enough at the
#: start that interrupting the panel works.
TURN_DETECTION = {
    "config": {
        "speech_threshold": 0.5,
        "start_of_speech": {
            "mode": "vad",
            "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300},
        },
        "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}},
    }
}
INTERRUPTION = {"enable": True}
#: RTM carries the agent's own transcript events back to the browser, which is
#: how the candidate sees what was heard while it is being said.
ADVANCED_FEATURES = {"enable_rtm": True}
PARAMETERS = {
    "audio_scenario": "chorus",
    "data_channel": "rtm",
    "enable_error_message": True,
    "enable_metrics": True,
}

#: The agent states worth rejoining. Everything else — `STOPPED`, `FAILED`, or
#: some status Agora adds later — counts as gone, because starting a second
#: agent costs a few seconds and rejoining one that is not there costs the
#: candidate an interview nobody speaks in.
LIVE_AGENT_STATUSES = frozenset({"STARTING", "RUNNING"})


@dataclass
class JoinData:
    """What a browser needs to join the interview's channel, and who else is in it."""

    enabled: bool
    app_id: str = ""
    channel: str = ""
    uid: int = 0
    token: str = ""
    agent_uid: int = 0
    agent_id: str = ""


class VoiceService(Protocol):
    enabled: bool

    def make_join(
        self,
        interview_id: str,
        *,
        uid: int | None = None,
        agent_uid: int | None = None,
        agent_id: str = "",
    ) -> JoinData: ...

    async def start_agent(
        self,
        join: JoinData,
        *,
        llm_url: str,
        llm_token: str,
        greeting: str,
        instructions: str,
    ) -> str: ...

    async def agent_is_live(self, agent_id: str) -> bool: ...

    async def stop_agent(self, agent_id: str) -> None: ...

    async def say(self, agent_id: str, text: str, *, interrupt: bool = False) -> None: ...

    async def interrupt(self, agent_id: str) -> None: ...


#: How a configured agent becomes a session. Injectable so tests can watch what
#: is asked of the session without an Agora project behind it.
SessionFactory = Callable[[Agent, JoinData], Any]


def _open_session(agent: Agent, join: JoinData) -> Any:
    return agent.create_async_session(
        channel=join.channel,
        agent_uid=str(join.agent_uid),
        remote_uids=[str(join.uid)],
        # Without a name the SDK invents `agent-{unix seconds}`, which two
        # interviews starting in the same second would share. Agora will not
        # take the same name twice, so the suffix is per attempt, not per
        # interview: a start that failed after Agora made the agent must not
        # poison every retry.
        name=f"{join.channel}-{secrets.token_hex(4)}",
        idle_timeout=IDLE_TIMEOUT_SECONDS,
        enable_string_uid=False,
        expires_in=TOKEN_TTL_SECONDS,
    )


class AgoraVoiceService:
    """One Agora Conversational AI agent per interview, held for its session."""

    enabled = True

    def __init__(
        self,
        settings: Settings,
        *,
        client: Any = None,
        session_factory: SessionFactory = _open_session,
    ):
        self._settings = settings
        self._client = client if client is not None else _build_client(settings)
        self._session_factory = session_factory
        # The sessions this process started. An agent started before a restart
        # has no session here, but Agora still knows its id, so every call falls
        # back to the REST client (`client.agents.*`) for one of those.
        self._sessions: dict[str, Any] = {}

    def make_join(
        self,
        interview_id: str,
        *,
        uid: int | None = None,
        agent_uid: int | None = None,
        agent_id: str = "",
    ) -> JoinData:
        """Mint the channel and the credentials for one interview's conversation.

        Given the identities of a conversation already in progress, it re-mints a
        token for that one instead of inventing a new one: a reloaded page
        rejoins the agent it left, and the agent goes on answering the uid it was
        started to listen to.
        """
        channel = f"quorum-{interview_id}"
        # Two publishers share the channel: the candidate's browser and the
        # agent. The ranges keep them apart at a glance in Agora's console.
        uid = uid or random.randint(1_000, 9_999_999)
        return JoinData(
            enabled=True,
            app_id=self._settings.AGORA_APP_ID,
            channel=channel,
            uid=uid,
            token=generate_convo_ai_token(
                app_id=self._settings.AGORA_APP_ID,
                app_certificate=self._settings.AGORA_APP_CERTIFICATE,
                channel_name=channel,
                uid=uid,
                token_expire=TOKEN_TTL_SECONDS,
            ),
            agent_uid=agent_uid or random.randint(10_000_000, 99_999_999),
            agent_id=agent_id,
        )

    async def start_agent(
        self,
        join: JoinData,
        *,
        llm_url: str,
        llm_token: str,
        greeting: str,
        instructions: str,
    ) -> str:
        """Put an agent in the channel and return the id Agora knows it by."""
        session = self._open(
            join,
            llm_url=llm_url,
            llm_token=llm_token,
            greeting=greeting,
            instructions=instructions,
        )
        agent_id = await session.start()
        self._sessions[agent_id] = session
        logger.info("voice agent %s joined channel %s", agent_id, join.channel)
        return agent_id

    async def agent_is_live(self, agent_id: str) -> bool:
        """Whether Agora still has this agent in a channel.

        An agent hangs up by itself after `IDLE_TIMEOUT_SECONDS` with nobody
        there, so a stored id outlives the agent it names whenever a browser is
        away that long — a reload and a walk, a sleeping laptop, a dropped
        connection. Asking costs one round trip; assuming costs a session where
        the candidate holds a valid token and nothing ever speaks.
        """
        try:
            info = await self._client.agents.get(self._settings.AGORA_APP_ID, agent_id)
        except Exception as failure:
            # Unreachable, unknown id, refused: none of them are an agent to
            # rejoin, and the caller's answer to all three is to start a new one.
            logger.warning(
                "could not read the state of voice agent %s (%s)",
                agent_id,
                type(failure).__name__,
            )
            logger.debug("voice agent %s state unreadable", agent_id, exc_info=failure)
            return False
        return getattr(info, "status", None) in LIVE_AGENT_STATUSES

    async def stop_agent(self, agent_id: str) -> None:
        """Take the agent out of the channel; an interview ends either way."""
        session = self._sessions.pop(agent_id, None)
        try:
            if session is not None:
                await session.stop()
            else:
                await self._client.agents.stop(self._settings.AGORA_APP_ID, agent_id)
        except Exception:
            # Nothing downstream can act on this, and an agent nobody stopped
            # hangs up on its own after `idle_timeout`.
            logger.exception("could not stop voice agent %s", agent_id)
            # Reported, not raised: the caller counts it as a provider failure.
            return False
        return True

    async def say(self, agent_id: str, text: str, *, interrupt: bool = False) -> None:
        """Speak a line the model endpoint was never asked for.

        Callers speak inline, in the middle of a turn, so nothing here is worth
        raising over: a line the candidate did not hear is not a lost interview.
        """
        session = self._sessions.get(agent_id)
        priority = "INTERRUPT" if interrupt else "APPEND"
        try:
            if session is not None:
                await session.say(text, priority=priority, interruptable=True)
            else:
                await self._client.agents.speak(
                    self._settings.AGORA_APP_ID,
                    agent_id,
                    text=text,
                    priority=priority,
                    interruptable=True,
                )
        except Exception as failure:
            self._forget(agent_id, "speak", failure)

    async def interrupt(self, agent_id: str) -> None:
        """Stop the agent mid-sentence, as a person talking over it would."""
        session = self._sessions.get(agent_id)
        try:
            if session is not None:
                await session.interrupt()
            else:
                await self._client.agents.interrupt(self._settings.AGORA_APP_ID, agent_id)
        except Exception as failure:
            self._forget(agent_id, "interrupt", failure)

    def build_properties(
        self,
        join: JoinData,
        *,
        llm_url: str,
        llm_token: str,
        greeting: str,
        instructions: str,
    ) -> dict:
        """The start request `start_agent` would send, resolved without sending it.

        `Agent.to_properties` cannot produce it alone: it validates every vendor
        block against the bring-your-own-key wire models, which the
        Agora-managed Deepgram and MiniMax blocks do not fit. The session
        resolves the body `start()` posts — skipping those two categories and
        folding them into a preset — so it is asked here rather than having its
        rules restated.
        """
        session = self._open(
            join,
            llm_url=llm_url,
            llm_token=llm_token,
            greeting=greeting,
            instructions=instructions,
        )
        # Derived, not hardcoded, so the seam cannot disagree with `start()`
        # about which vendors are Agora-managed.
        skip, allow_missing = session._vendor_validation_categories(None)
        return session._build_start_properties(
            {
                "app_id": self._settings.AGORA_APP_ID,
                "app_certificate": self._settings.AGORA_APP_CERTIFICATE,
                "expires_in": TOKEN_TTL_SECONDS,
            },
            skip,
            allow_missing,
        )

    def _open(
        self,
        join: JoinData,
        *,
        llm_url: str,
        llm_token: str,
        greeting: str,
        instructions: str,
    ) -> Any:
        """Configure the agent for one interview and bind it to one channel."""
        agent = Agent(
            self._client,
            instructions=instructions,
            # Agora speaks the opening line itself. The endpoint has no turn to
            # answer before the candidate says anything, and a synthetic empty
            # one is rejected there.
            greeting=greeting,
            failure_message=FAILURE_MESSAGE,
            max_history=MAX_HISTORY,
            turn_detection=TURN_DETECTION,
            interruption=INTERRUPTION,
            advanced_features=ADVANCED_FEATURES,
            parameters=PARAMETERS,
        )
        agent = (
            agent.with_stt(DeepgramSTT(model=self._settings.AGORA_ASR_MODEL, language="en"))
            .with_llm(
                CustomLLM(
                    base_url=llm_url,
                    api_key=llm_token,
                    model=CONTROLLER_MODEL,
                    greeting_message=greeting,
                    failure_message=FAILURE_MESSAGE,
                    max_history=MAX_HISTORY,
                    max_tokens=MAX_SPOKEN_TOKENS,
                    temperature=SPOKEN_TEMPERATURE,
                )
            )
            .with_tts(
                MiniMaxTTS(
                    model=self._settings.AGORA_TTS_MODEL,
                    voice_id=self._settings.AGORA_TTS_VOICE_ID,
                )
            )
        )
        return self._session_factory(agent, join)

    def _forget(self, agent_id: str, what: str, failure: Exception) -> None:
        """Stop holding a session that has stopped answering.

        An agent that hit Agora's idle timeout is gone, and the next call would
        raise the same way. Dropping the session sends every later call through
        the REST client, which fails the same quiet way. The message stays out
        of the log: an SDK error can quote the request it failed on, bearer and
        all.
        """
        self._sessions.pop(agent_id, None)
        logger.warning(
            "could not %s: voice agent %s is no longer live (%s)",
            what,
            agent_id,
            type(failure).__name__,
        )
        logger.debug("voice agent %s failed to %s", agent_id, what, exc_info=failure)


class NullVoiceService:
    """Text mode: `/start` reports voice off and every other call does nothing."""

    enabled = False

    def make_join(
        self,
        interview_id: str,
        *,
        uid: int | None = None,
        agent_uid: int | None = None,
        agent_id: str = "",
    ) -> JoinData:
        return JoinData(enabled=False)

    async def agent_is_live(self, agent_id: str) -> bool:
        return False

    async def start_agent(
        self,
        join: JoinData,
        *,
        llm_url: str,
        llm_token: str,
        greeting: str,
        instructions: str,
    ) -> str:
        return ""

    async def stop_agent(self, agent_id: str) -> None:
        return None

    async def say(self, agent_id: str, text: str, *, interrupt: bool = False) -> None:
        return None

    async def interrupt(self, agent_id: str) -> None:
        return None


def build_voice(settings: Settings) -> VoiceService:
    """The voice service this deployment can actually run, and why."""
    if not settings.voice_configured:
        logger.info(
            "voice is off: AGORA_APP_ID and AGORA_APP_CERTIFICATE are not both set"
        )
        return NullVoiceService()
    if not settings.llm_endpoint_enabled:
        logger.info(
            "voice is off: the agent reaches its model over the public internet and "
            "needs CUSTOM_LLM_PUBLIC_BASE_URL and CUSTOM_LLM_AUTH_SECRET to do it"
        )
        return NullVoiceService()
    logger.info("voice is on: Agora Conversational AI, %s speech to text", settings.AGORA_ASR_MODEL)
    return AgoraVoiceService(settings)


def _build_client(settings: Settings) -> AsyncAgora:
    return AsyncAgora(
        area=Area.US,
        app_id=settings.AGORA_APP_ID,
        app_certificate=settings.AGORA_APP_CERTIFICATE,
    )
