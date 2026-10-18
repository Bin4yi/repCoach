"""FastAPI dependencies: db access, coach auth (MVP: one password, signed cookie), client token lookup."""
from __future__ import annotations

import hashlib
import hmac

from fastapi import Depends, HTTPException, Request

COOKIE_NAME = "repcheck_coach"


def coach_cookie_value(password: str) -> str:
    # The cookie is an HMAC of a fixed label keyed by the coach password. MVP only: one coach account.
    return hmac.new(password.encode(), b"repcheck-coach-session", hashlib.sha256).hexdigest()


def get_db(request: Request):
    return request.app.state.db


def get_settings_dep(request: Request):
    return request.app.state.settings


async def require_coach(request: Request) -> None:
    cookie = request.cookies.get(COOKIE_NAME, "")
    expected = coach_cookie_value(request.app.state.settings.coach_password)
    if not hmac.compare_digest(cookie, expected):
        raise HTTPException(status_code=401, detail="Coach login required")


async def client_by_token(token: str, db=Depends(get_db)) -> dict:
    client = await db.clients.find_one({"token": token})
    if not client:
        raise HTTPException(status_code=404, detail="This link is not valid.")
    return client
