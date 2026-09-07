"""Exchanging a capability token for the cookie that carries it.

The reviewer is handed a token once, in the link the candidate copies; this is
where that link becomes a session.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.routes.deps import (
    COOKIE_FOR_KIND,
    hash_token,
    require_same_origin,
    set_capability_cookie,
)
from app.storage import repo

mutations = APIRouter(
    prefix="/api/auth", tags=["auth"], dependencies=[Depends(require_same_origin)]
)


class ExchangeRequest(BaseModel):
    token: str


@mutations.post("/exchange")
async def exchange_token(body: ExchangeRequest, request: Request, response: Response) -> dict:
    settings = request.app.state.settings
    conn = request.app.state.db

    capability = repo.find_capability(conn, hash_token(settings, body.token))
    if capability is None or repo.get_interview(conn, capability["interview_id"]) is None:
        raise HTTPException(404, "this link is not valid")

    set_capability_cookie(response, COOKIE_FOR_KIND[capability["kind"]], body.token, settings)
    return {"interview_id": capability["interview_id"], "kind": capability["kind"]}
