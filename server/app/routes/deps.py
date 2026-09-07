"""Capability-cookie authentication and the same-origin guard for mutations.

An interview has no accounts. Whoever holds a capability token is the candidate
or the reviewer of exactly one interview, and the token only ever reaches the
database as an HMAC, so a copy of the database hands out no sessions.
"""

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

from app.config import Settings
from app.storage import repo

COOKIE_CANDIDATE = "quorum_candidate"
COOKIE_REVIEWER = "quorum_reviewer"
COOKIE_FOR_KIND = {"candidate": COOKIE_CANDIDATE, "reviewer": COOKIE_REVIEWER}
#: Carries `DEMO_ACCESS_KEY` on `POST /api/interviews`; the web app reads it
#: from `NEXT_PUBLIC_DEMO_ACCESS_KEY`.
ACCESS_KEY_HEADER = "X-Quorum-Access-Key"

SECONDS_PER_DAY = 86_400


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


def require_access_key(request: Request) -> None:
    """Refuse to create an interview without the demo access key, when one is set.

    A voice deployment is reachable from the public internet by design (Agora
    calls back into it), and the Origin check is a header any client can send.
    The key is what stops a public demo from starting unlimited paid sessions
    (PRD section 15); with `DEMO_ACCESS_KEY` empty the route is open.
    """
    expected = request.app.state.settings.DEMO_ACCESS_KEY
    if not expected:
        return
    presented = request.headers.get(ACCESS_KEY_HEADER, "")
    if not hmac.compare_digest(expected.encode(), presented.encode()):
        raise HTTPException(403, "this deployment needs an access key to start an interview")


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
