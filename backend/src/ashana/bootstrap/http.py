"""HTTP helpers shared by every module's routes: settings, session cookie, CSRF, results."""

import hashlib
import secrets
from typing import cast
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel

from ashana.bootstrap.settings import Settings
from ashana.modules.identity.domain.models import IdentityError


def settings_for(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def session_token(request: Request) -> str:
    return request.cookies.get(settings_for(request).session_cookie, "")[:256]


def csrf_for_session(token: str) -> str:
    # Domain separation keeps the CSRF token distinct from the HttpOnly bearer credential.
    return hashlib.sha256(f"ashana-csrf:{token}".encode()).hexdigest()


def enforce_csrf(request: Request) -> None:
    settings = settings_for(request)
    if request.headers.get("origin") not in settings.allowed_origins:
        raise IdentityError("CSRF_FAILED", "Обновите страницу и повторите действие")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise IdentityError("CSRF_FAILED", "Обновите страницу и повторите действие")
    token = session_token(request)
    expected = csrf_for_session(token) if token else request.cookies.get(settings.csrf_cookie, "")
    supplied = request.headers.get("x-csrf-token", "")
    if (
        not expected
        or not supplied
        or len(supplied) > 128
        or not secrets.compare_digest(expected, supplied)
    ):
        raise IdentityError("CSRF_FAILED", "Обновите страницу и повторите действие")


class OperationResponse(BaseModel):
    subject_id: UUID
    version: int
