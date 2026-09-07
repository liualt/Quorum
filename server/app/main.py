"""FastAPI app factory: settings, database, event bus, lifespan wiring."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.scenario import load_scenario
from app.storage import db, repo
from app.storage.events import EventBus


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
    # task 3: executor
    # task 5: llm
    # task 6: controller
    # task 7: voice

    yield

    # task 8: evidence hooks + cleanup
    connection.close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(lifespan=lifespan)
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health():
        executor = getattr(app.state, "executor", None)
        return {
            "status": "ok",
            "executor": getattr(executor, "name", "none"),
            "llm_provider": settings.LLM_PROVIDER,
            "llm_model": settings.LLM_MODEL,
            "voice_enabled": settings.voice_configured,
        }

    return app
