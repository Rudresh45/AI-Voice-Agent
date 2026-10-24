"""Identity and Authentication domain API routers."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    get_current_user,
    get_current_user_session,
    get_db,
)
from app.db.models import User, UserSession
from app.modules.identity.schemas import (
    LoginRequest,
    LoginResponse,
    LogoutResponse,
    PasswordSetRequest,
    UserProfileResponse,
    UserRead,
    UserSessionRead,
    UserUpdate,
)
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/identity", tags=["Identity"])
auth_router = APIRouter(prefix="/auth", tags=["Authentication"])


# --- Authentication Endpoints ---

@auth_router.post("/login", response_model=LoginResponse, summary="Log in with email and password")
def login(
    data: LoginRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> LoginResponse:
    service = IdentityService(db)
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    token, session, user = service.login(
        email=data.email,
        password=data.password,
        ip_address=client_ip,
        user_agent=user_agent,
    )
    return LoginResponse(
        session_token=token,
        expires_at=session.expires_at,
        user=UserRead.model_validate(user),
    )


@auth_router.post("/logout", response_model=LogoutResponse, summary="Log out and revoke current session")
def logout(
    db: Annotated[Session, Depends(get_db)],
    current_session: Annotated[UserSession | None, Depends(get_current_user_session)],
) -> LogoutResponse:
    if current_session is not None:
        service = IdentityService(db)
        service.logout_session(current_session)
    return LogoutResponse(message="Session successfully revoked.")


# --- User Profile & Session Management Endpoints ---

@router.get("/me", response_model=UserProfileResponse, summary="Get current user profile")
def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserProfileResponse:
    service = IdentityService(db)
    return service.get_profile(current_user)


@router.patch("/me", response_model=UserRead, summary="Update current user profile")
def update_me(
    data: UserUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    service = IdentityService(db)
    return service.update_profile(current_user.id, data)


@router.post("/me/password", status_code=status.HTTP_204_NO_CONTENT, summary="Set user password")
def set_password(
    data: PasswordSetRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    service = IdentityService(db)
    service.set_user_password(current_user.id, data.password)


@router.get("/sessions", response_model=list[UserSessionRead], summary="List active user sessions")
def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserSessionRead]:
    service = IdentityService(db)
    return service.list_active_sessions(current_user.id)


@router.delete("/sessions/{session_id}", response_model=LogoutResponse, summary="Revoke a specific user session")
def revoke_session(
    session_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> LogoutResponse:
    service = IdentityService(db)
    service.revoke_session(session_id, current_user.id)
    return LogoutResponse(message="Session revoked.")
