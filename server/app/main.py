"""FastAPI app factory: settings, database, event bus, lifespan wiring."""

import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from weakref import WeakValueDictionary

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import background, cleanup, ids
from app.config import Settings, get_settings
from app.evidence.claims import extract_and_store_claims
from app.evidence.disputes import mark_findings_needing_review
from app.evidence.links import link_run_to_claims
from app.execution.executor import build_executor
from app.execution.runs import recover_interrupted_runs
from app.interview.agora import build_voice
from app.interview import watchdog
from app.interview.controller import InterviewController
from app.interview.llm_client import build_llm
from app.routes import assessment, auth, events, files, interviews, llm, runs, turns
from app.scenario import load_scenario
from app.storage import db, repo
from app.storage.events import EventBus

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    os.makedirs(os.path.dirname(settings.DATABASE_PATH) or ".", exist_ok=True)
    os.makedirs(settings.SNAPSHOT_DIR, exist_ok=True)

    connection = db.connect(settings.DATABASE_PATH)
    db.init_schema(connection)
    app.state.db = connection
    app.state.bus = EventBus()
    # Shared with repo's internal write lock so callers outside app.storage.repo
    # can serialize compound operations against the same lock repo writes hold.
    app.state.write_lock = repo._lock

    scenario_dir = Path(settings.SCENARIO_DIR)
    if not scenario_dir.is_absolute():
        scenario_dir = Path(__file__).resolve().parents[1] / scenario_dir
    app.state.scenario = load_scenario(scenario_dir, settings.SCENARIO_ID)
    app.state.executor = build_executor(settings)
    app.state.llm = build_llm(settings)
    app.state.background_tasks = set()
    app.state.voice = build_voice(settings)
    app.state.controller = InterviewController(app)
    # One lock per interview for `/finish`, apart from the controller's turn lock:
    # finishing awaits the claim extractions, which take the turn lock themselves.
    app.state.finish_locks = WeakValueDictionary()

    # The evidence hooks earlier modules reach through `getattr`: the controller
    # schedules claim extraction and hands completed runs to the linker, and the
    # run service marks findings when a replay disagrees with its original.
    app.state.claims_extractor = extract_and_store_claims
    app.state.link_run = lambda interview_id, run_row: link_run_to_claims(
        app.state.db, interview_id, run_row
    )
    app.state.mark_findings_needing_review = (
        lambda interview_id, ref_type, ref_id, reason: mark_findings_needing_review(
            app.state.db, app.state.bus, interview_id, ref_type, ref_id, reason
        )
    )

    await cleanup.expire_interviews(app, ids.now_iso())
    recover_interrupted_runs(app)
    background.spawn_periodic(
        app,
        lambda: cleanup.expire_interviews(app, ids.now_iso()),
        cleanup.EXPIRY_INTERVAL_SECONDS,
        "expiry",
    )
    # Ends live sessions at the cap whether or not another turn arrives (A07).
    background.spawn_periodic(
        app,
        lambda: watchdog.sweep_sessions(app),
        settings.SESSION_WATCHDOG_INTERVAL_SECONDS,
        "session_watchdog",
    )

    yield

    await background.cancel_all(app)
    connection.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if not settings.SESSION_SECRET:
        # Never key every capability hash with a known empty string. A secret
        # that lasts one process keeps the links working until the next
        # restart, which is the loudest a default can safely be.
        settings.SESSION_SECRET = secrets.token_urlsafe(32)
        logger.warning(
            "SESSION_SECRET is not set: using a random secret for this process, so every "
            "candidate and reviewer link stops working when the server restarts"
        )

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Two routers per concern: the `mutations` ones carry the same-origin guard
    # as a router-level dependency, so no non-GET route can be added without it.
    app.include_router(interviews.router)
    app.include_router(interviews.mutations)
    app.include_router(interviews.admission)
    app.include_router(files.router)
    app.include_router(files.mutations)
    app.include_router(runs.router)
    app.include_router(runs.mutations)
    app.include_router(events.router)
    app.include_router(auth.mutations)
    app.include_router(turns.mutations)
    app.include_router(assessment.router)
    app.include_router(assessment.mutations)
    # The voice agent's endpoint: bearer-authenticated, outside /api and its guards.
    app.include_router(llm.router)

    @app.get("/api/health")
    async def health():
        executor = getattr(app.state, "executor", None)
        llm = getattr(app.state, "llm", None)
        voice = getattr(app.state, "voice", None)
        return {
            "status": "ok",
            "executor": getattr(executor, "name", "none"),
            "llm_provider": settings.LLM_PROVIDER,
            "llm_model": getattr(llm, "model_id", settings.LLM_MODEL),
            "voice_enabled": voice.enabled if voice is not None else settings.voice_configured,
        }

    return app
