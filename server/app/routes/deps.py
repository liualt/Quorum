"""Capability-cookie authentication and the same-origin guard for mutations.

An interview has no accounts. Whoever holds a capability token is the candidate
or the reviewer of exactly one interview, and the token only ever reaches the
database as an HMAC, so a copy of the database hands out no sessions.
"""

import hashlib
import hmac
import secrets
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.config import Settings
from app.storage import repo

COOKIE_CANDIDATE = "quorum_candidate"
COOKIE_REVIEWER = "quorum_reviewer"
COOKIE_FOR_KIND = {"candidate": COOKIE_CANDIDATE, "reviewer": COOKIE_REVIEWER}
#: Carries `DEMO_ACCESS_KEY` on `POST /api/interviews`. The web app sends the
#: key the candidate typed as the `access_key` body field instead; either works.
ACCESS_KEY_HEADER = "X-Access-Key"

SECONDS_PER_DAY = 86_400
SECONDS_PER_HOUR = 3_600
#: The per-IP window key that also counts every create, whatever its IP.
_TOTAL = "*"


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(settings: Settings, token: str) -> str:
    """The stored form of a capability token."""
    return hmac.new(
        settings.SESSION_SECRET.encode(), token.encode(), hashlib.sha256
    ).hexdigest()


def llm_token(settings: Settings, interview_id: str) -> str:
    """The bearer token the voice agent presents on /llm/{id}/chat/completions.

    Keyed separately from session cookies so the agent's credential and a
    candidate's session never derive from the same secret.
    """
    return hmac.new(
        settings.CUSTOM_LLM_AUTH_SECRET.encode(), interview_id.encode(), hashlib.sha256
    ).hexdigest()


def set_capability_cookie(response, name: str, token: str, settings: Settings) -> None:
    """Store a capability token in the browser for the interview's whole life."""
    response.set_cookie(
        name,
        token,
        httponly=True,
        samesite="lax",
        secure=any(origin.startswith("https://") for origin in settings.allowed_origins),
        path="/",
        max_age=settings.RETENTION_DAYS * SECONDS_PER_DAY,
    )


def require_same_origin(request: Request) -> None:
    """Refuse a mutation that did not come from a page this backend serves.

    Cookies are `SameSite=lax`, which still lets a cross-site form POST carry
    them; this is the check that stops one.
    """
    origin = request.headers.get("origin") or _referer_origin(request)
    if origin not in request.app.state.settings.allowed_origins:
        raise HTTPException(403, "this request did not come from an allowed origin")


def access_key_required(settings: Settings) -> bool:
    return bool(settings.DEMO_ACCESS_KEY)


def require_access_key(request: Request, body_key: str | None = None) -> None:
    """Refuse to create an interview without the demo access key, when one is set.

    A voice deployment is reachable from the public internet by design (Agora
    calls back into it), and the Origin check is a header any client can send.
    The key is what stops a public demo from starting unlimited paid sessions
    (PRD section 15); with `DEMO_ACCESS_KEY` empty the route is open. The key
    may arrive in the `X-Access-Key` header or as the `access_key` body field,
    which is what the consent form sends.
    """
    expected = request.app.state.settings.DEMO_ACCESS_KEY
    if not expected:
        return
    presented = request.headers.get(ACCESS_KEY_HEADER) or body_key or ""
    if not presented.strip():
        raise HTTPException(403, "this deployment needs an access key to start an interview")
    if not hmac.compare_digest(expected.encode(), presented.strip().encode()):
        raise HTTPException(403, "that access key is not valid for this deployment")


class CreateQuota:
    """A per-process sliding window over interview creations, per IP and in total.

    Per-IP alone would not bound spend: the web app proxies `/api` through
    Next.js, so every browser can look like one address, and a public
    deployment may sit behind a proxy that rewrites the address anyway. The
    total window is the bound; the per-IP window only stops one client from
    using it all up when addresses are distinguishable.
    """

    def __init__(self, limit_per_hour: int) -> None:
        self.limit = limit_per_hour
        self._windows: dict[str, deque[float]] = {}

    def _recent(self, key: str, now: float) -> deque[float]:
        window = self._windows.setdefault(key, deque())
        while window and window[0] <= now - SECONDS_PER_HOUR:
            window.popleft()
        return window

    def check(self, client_ip: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for key in (client_ip, _TOTAL):
            if len(self._recent(key, now)) >= self.limit:
                raise HTTPException(
                    429,
                    f"this deployment allows {self.limit} new interviews per hour;"
                    " please try again later",
                )

    def record(self, client_ip: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        for key in (client_ip, _TOTAL):
            self._recent(key, now).append(now)


def create_quota(request: Request) -> CreateQuota:
    """The process-wide creation window, made on first use so tests get a fresh one per app."""
    state = request.app.state
    quota = getattr(state, "create_quota", None)
    if quota is None:
        quota = state.create_quota = CreateQuota(state.settings.MAX_INTERVIEWS_PER_HOUR)
    return quota


def client_ip(request: Request) -> str:
    """The address the hourly window is keyed by: the first forwarded hop, else the peer."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def require_creation_quota(request: Request) -> None:
    """Refuse a create that would exceed the hourly window or the active-interview cap.

    Both apply whether or not an access key is configured: a leaked key must
    not turn into unlimited paid sessions either. The caller records the
    creation with `create_quota(request).record(...)` once it has happened, so
    a refused or failed create does not use up the window.
    """
    settings = request.app.state.settings
    create_quota(request).check(client_ip(request))
    active = repo.count_active_interviews(request.app.state.db)
    if active >= settings.MAX_ACTIVE_INTERVIEWS:
        raise HTTPException(
            429,
            f"this deployment allows {settings.MAX_ACTIVE_INTERVIEWS} interviews in progress"
            " at once; please try again once one has finished",
        )


def _referer_origin(request: Request) -> str | None:
    parts = urlsplit(request.headers.get("referer", ""))
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


async def require_candidate(interview_id: str, request: Request):
    row, _ = _authorise(request, interview_id, ("candidate",))
    return row


async def require_reviewer(interview_id: str, request: Request):
    row, _ = _authorise(request, interview_id, ("reviewer",))
    return row


async def require_participant(interview_id: str, request: Request) -> tuple[object, str]:
    """The interview row and which side of it the caller is on."""
    return _authorise(request, interview_id, ("candidate", "reviewer"))


def _authorise(request: Request, interview_id: str, accepted: tuple[str, ...]):
    """Resolve the caller's capability, or raise the refusal it has earned.

    Every cookie is read, not only the accepted ones: a reviewer reaching a
    candidate route is signed in and refused (403), not asked to sign in (401).
    Existence is only disclosed to a caller presenting some capability at all,
    and a deleted interview then answers 404 even to the cookie that created
    it, so the browser can tell "gone" from "not yours".
    """
    presented = [
        (kind, request.cookies[cookie])
        for kind, cookie in COOKIE_FOR_KIND.items()
        if request.cookies.get(cookie)
    ]
    if not presented:
        raise HTTPException(401, "this interview needs its access link")

    conn = request.app.state.db
    row = repo.get_interview(conn, interview_id)
    if row is None or row["status"] == "deleted":
        raise HTTPException(404, "interview not found")

    settings = request.app.state.settings
    held = []
    for kind, token in presented:
        capability = repo.find_capability(conn, hash_token(settings, token))
        # A token presented in the other side's cookie is not that side.
        if capability is not None and capability["kind"] == kind:
            held.append(capability)
    if not held:
        raise HTTPException(401, "this access link is no longer valid")

    for kind in accepted:  # in the caller's order of preference
        for capability in held:
            if capability["kind"] == kind and capability["interview_id"] == interview_id:
                return row, kind
    raise HTTPException(403, "this access link is not for this interview")
