"""ID and timestamp helpers shared across the backend."""

import secrets
from datetime import UTC, datetime


def new_id(prefix: str) -> str:
    """Return an opaque id like 'itv_a1b2c3d4e5f6a7b8'."""
    return f"{prefix}_{secrets.token_hex(8)}"


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string ending in 'Z'."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
