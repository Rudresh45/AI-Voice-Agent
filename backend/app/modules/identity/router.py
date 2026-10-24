"""Identity domain API router."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.modules.identity.models import User
from app.modules.identity.schemas import UserProfileResponse, UserRead, UserUpdate
from app.modules.identity.service import IdentityService

router = APIRouter(prefix="/identity", tags=["Identity"])


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
