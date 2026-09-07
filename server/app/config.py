"""Application settings, loaded from environment / .env with sane defaults."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AGORA_APP_ID: str = ""
    AGORA_APP_CERTIFICATE: str = ""
    AGORA_ASR_MODEL: str = "nova-3"
    AGORA_TTS_MODEL: str = "speech_2_6_turbo"
    AGORA_TTS_VOICE_ID: str = "English_captivating_female1"

    CUSTOM_LLM_PUBLIC_BASE_URL: str = ""
    CUSTOM_LLM_AUTH_SECRET: str = ""

    LLM_PROVIDER: str = "openai"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = ""
    LLM_MODEL: str = ""

    E2B_API_KEY: str = ""
    EXECUTOR: str = "e2b"

    SESSION_SECRET: str = ""
    # When set, `POST /api/interviews` needs it in the `X-Access-Key` header or
    # the `access_key` body field. `GET /api/admission` tells the web app so.
    DEMO_ACCESS_KEY: str = ""
    # Creation quotas, enforced whether or not a key is configured. The hourly
    # cap is a per-process sliding window, applied per client IP and in total;
    # the active cap counts interviews not yet finished or deleted.
    MAX_INTERVIEWS_PER_HOUR: int = 20
    MAX_ACTIVE_INTERVIEWS: int = 10

    DATABASE_PATH: str = "./data/quorum.db"
    SNAPSHOT_DIR: str = "./data/snapshots"

    ALLOWED_ORIGINS: str = "http://localhost:3000"

    RETENTION_DAYS: int = 7
    RUN_TIMEOUT_SECONDS: int = 20
    RUN_OUTPUT_CAP_BYTES: int = 65536
    SOURCE_LIMIT_BYTES: int = 102400
    MAX_RUNS_PER_INTERVIEW: int = 20
    SESSION_CAP_MINUTES: int = 30
    # How often the watchdog finishes live interviews past the cap (A07).
    SESSION_WATCHDOG_INTERVAL_SECONDS: float = 15.0

    SCENARIO_DIR: str = "../scenarios"
    FOLLOW_UP_DELAY_SECONDS: float = 6.0
    SCENARIO_ID: str = "document-search"

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def voice_configured(self) -> bool:
        return bool(self.AGORA_APP_ID and self.AGORA_APP_CERTIFICATE)

    @property
    def llm_endpoint_enabled(self) -> bool:
        return bool(self.CUSTOM_LLM_AUTH_SECRET and self.CUSTOM_LLM_PUBLIC_BASE_URL)


@lru_cache
def get_settings() -> Settings:
    return Settings()
