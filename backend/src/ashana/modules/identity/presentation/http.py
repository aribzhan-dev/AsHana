import hashlib
import secrets
from datetime import datetime
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ashana.bootstrap.errors import ErrorResponse
from ashana.bootstrap.settings import Settings
from ashana.modules.identity.application.service import IdentityService
from ashana.modules.identity.domain.models import IdentityError, User

router = APIRouter(
    prefix="/api/v1",
    tags=["Сотрудники"],
    responses={status: {"model": ErrorResponse} for status in (401, 403, 404, 409, 422, 429)},
)


def settings_for(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def service_for(request: Request) -> IdentityService:
    return cast(IdentityService, request.app.state.identity)


Service = Annotated[IdentityService, Depends(service_for)]


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


def clear_cookies(request: Request, response: Response) -> None:
    settings = settings_for(request)
    for name in (settings.session_cookie, settings.csrf_cookie):
        response.delete_cookie(
            name, path="/", secure=settings.cookie_secure, httponly=True, samesite="lax"
        )


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)


class LoginInput(InputModel):
    login: str = Field(min_length=1, max_length=64)
    password: SecretStr = Field(min_length=1, max_length=128)


class StaffInput(LoginInput):
    nickname: str = Field(default="", max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    telegram: str | None = Field(default=None, max_length=60)
    name: str = Field(min_length=1, max_length=100)
    roles: list[str] = Field(min_length=1, max_length=100)


class RolesInput(InputModel):
    roles: list[str] = Field(min_length=1, max_length=100)


class SearchInput(InputModel):
    login: str = Field(min_length=1, max_length=64)


def parse_roles(values: list[str]) -> frozenset[str]:
    return frozenset(values)


class UserResponse(BaseModel):
    nickname: str = ""
    id: UUID
    login: str
    phone: str | None
    name: str
    roles: list[str]
    permissions: list[str]
    is_demo: bool
    telegram: str | None = None
    is_active: bool = True
    created_at: datetime | None = None

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id,
            login=user.login,
            phone=user.phone,
            name=user.name,
            nickname=user.nickname,
            roles=sorted(user.roles),
            permissions=sorted(user.effective_permissions),
            is_demo=user.is_demo,
            telegram=user.telegram,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class CsrfResponse(BaseModel):
    csrf_token: str


class SessionResponse(BaseModel):
    id: UUID
    created_at: datetime
    expires_at: datetime
    current: bool


@router.get("/auth/csrf", operation_id="getCsrfToken")
def csrf(request: Request, response: Response) -> CsrfResponse:
    settings = settings_for(request)
    token = session_token(request)
    if token:
        return CsrfResponse(csrf_token=csrf_for_session(token))
    csrf_token = request.cookies.get(settings.csrf_cookie, "")
    if not 32 <= len(csrf_token) <= 128:
        csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        settings.csrf_cookie,
        csrf_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=3600,
    )
    return CsrfResponse(csrf_token=csrf_token)


@router.post("/auth/login", operation_id="loginStaff", dependencies=[Depends(enforce_csrf)])
def login(data: LoginInput, request: Request, response: Response, service: Service) -> UserResponse:
    settings = settings_for(request)
    user, token = service.login(
        data.login,
        data.password.get_secret_value(),
        request.client.host if request.client else "unknown",
        session_token(request),
    )
    response.set_cookie(
        settings.session_cookie,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        max_age=settings.session_seconds,
    )
    return UserResponse.from_user(user)


@router.get("/auth/me", operation_id="getCurrentStaff")
def me(request: Request, service: Service) -> UserResponse:
    return UserResponse.from_user(service.authenticate(session_token(request)).user)


@router.post(
    "/auth/logout",
    operation_id="logoutStaff",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
def logout(request: Request, response: Response, service: Service) -> None:
    service.logout(session_token(request))
    clear_cookies(request, response)


@router.get("/auth/sessions", operation_id="listOwnSessions")
def list_sessions(request: Request, service: Service) -> list[SessionResponse]:
    principal, sessions = service.sessions(session_token(request))
    return [
        SessionResponse(
            id=session.id,
            created_at=session.created_at,
            expires_at=session.expires_at,
            current=session.id == principal.session.id,
        )
        for session in sessions
    ]


@router.delete(
    "/auth/sessions/{session_id}",
    operation_id="revokeOwnSession",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
def revoke_session(
    session_id: UUID, request: Request, response: Response, service: Service
) -> None:
    current = service.revoke_session(session_token(request), session_id)
    if current:
        clear_cookies(request, response)


@router.post("/admin/users/search", operation_id="findStaff", dependencies=[Depends(enforce_csrf)])
def search_staff(data: SearchInput, request: Request, service: Service) -> UserResponse:
    return UserResponse.from_user(service.find_staff(session_token(request), data.login))


@router.post(
    "/admin/users",
    operation_id="createStaff",
    status_code=201,
    dependencies=[Depends(enforce_csrf)],
)
def create_staff(data: StaffInput, request: Request, service: Service) -> UserResponse:
    return UserResponse.from_user(
        service.create_staff(
            session_token(request),
            data.name,
            data.login,
            data.password.get_secret_value(),
            parse_roles(data.roles),
            phone=data.phone,
            nickname=data.nickname,
            telegram=data.telegram,
        )
    )


@router.put(
    "/admin/users/{user_id}/roles",
    operation_id="assignStaffRoles",
    dependencies=[Depends(enforce_csrf)],
)
def assign_roles(
    user_id: UUID, data: RolesInput, request: Request, service: Service
) -> UserResponse:
    return UserResponse.from_user(
        service.assign_roles(session_token(request), user_id, parse_roles(data.roles))
    )


class ProfileInput(InputModel):
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=32)
    telegram: str | None = Field(default=None, max_length=60)
    nickname: str = Field(default="", max_length=100)


class StatusInput(InputModel):
    active: bool


@router.get("/admin/users/{user_id}", operation_id="getStaff")
def staff_member(user_id: UUID, request: Request, service: Service) -> UserResponse:
    return UserResponse.from_user(service.staff_member(session_token(request), user_id))


@router.put(
    "/admin/users/{user_id}/profile",
    operation_id="updateStaffProfile",
    dependencies=[Depends(enforce_csrf)],
)
def update_profile(
    user_id: UUID, data: ProfileInput, request: Request, service: Service
) -> UserResponse:
    return UserResponse.from_user(
        service.update_profile(
            session_token(request), user_id, data.name, data.phone, data.telegram, data.nickname
        )
    )


@router.put(
    "/admin/users/{user_id}/status",
    operation_id="setStaffStatus",
    dependencies=[Depends(enforce_csrf)],
)
def set_status(
    user_id: UUID, data: StatusInput, request: Request, service: Service
) -> UserResponse:
    return UserResponse.from_user(service.set_active(session_token(request), user_id, data.active))


@router.delete(
    "/admin/users/{user_id}",
    operation_id="deleteStaff",
    status_code=204,
    dependencies=[Depends(enforce_csrf)],
)
def delete_staff(user_id: UUID, request: Request, service: Service) -> Response:
    service.delete_staff(session_token(request), user_id)
    return Response(status_code=204)


class PasswordResetInput(InputModel):
    password: SecretStr = Field(min_length=1, max_length=128)


@router.put(
    "/admin/users/{user_id}/password",
    operation_id="resetStaffPassword",
    dependencies=[Depends(enforce_csrf)],
)
def reset_password(
    user_id: UUID, data: PasswordResetInput, request: Request, service: Service
) -> UserResponse:
    return UserResponse.from_user(
        service.reset_password(session_token(request), user_id, data.password.get_secret_value())
    )


class RoleInput(InputModel):
    code: str = Field(min_length=3, max_length=20)
    name: str = Field(min_length=1, max_length=100)
    permissions: list[str] = Field(max_length=20)
    version: int | None = Field(default=None, ge=1)


class RoleResponse(BaseModel):
    code: str
    name: str
    permissions: list[str]
    version: int


@router.get("/admin/roles", operation_id="listRoles")
def list_roles(request: Request, service: Service) -> list[RoleResponse]:
    return [
        RoleResponse(code=r.code, name=r.name, permissions=sorted(r.permissions), version=r.version)
        for r in service.list_roles(session_token(request))
    ]


@router.put("/admin/roles", operation_id="saveRole", dependencies=[Depends(enforce_csrf)])
def save_role(data: RoleInput, request: Request, service: Service) -> RoleResponse:
    r = service.save_role(
        session_token(request), data.code, data.name, frozenset(data.permissions), data.version
    )
    return RoleResponse(
        code=r.code, name=r.name, permissions=sorted(r.permissions), version=r.version
    )


@router.get("/admin/users", operation_id="listStaff")
def list_staff(request: Request, service: Service, offset: int = 0) -> list[UserResponse]:
    return [
        UserResponse.from_user(user) for user in service.list_staff(session_token(request), offset)
    ]


class NicknameInput(InputModel):
    nickname: str = Field(max_length=100)
    expected_nickname: str = Field(max_length=100)


@router.put(
    "/admin/users/{user_id}/nickname",
    operation_id="setStaffNickname",
    dependencies=[Depends(enforce_csrf)],
)
def set_nickname(
    user_id: UUID, data: NicknameInput, request: Request, service: Service
) -> UserResponse:
    return UserResponse.from_user(
        service.set_nickname(session_token(request), user_id, data.nickname, data.expected_nickname)
    )
