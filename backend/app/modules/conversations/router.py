"""Conversations domain API router."""

import uuid
from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_tenant, get_current_user, get_db
from app.core.pagination import PageParams, PaginatedResponse
from app.db.models import Tenant, User
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
)
from app.modules.conversations.service import ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])


@router.post("/", response_model=ConversationRead, status_code=status.HTTP_201_CREATED, summary="Create conversation")
def create_conversation(
    data: ConversationCreate,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationRead:
    service = ConversationService(db)
    return service.create_conversation(current_tenant.id, current_user.id, data)


@router.get("/", response_model=PaginatedResponse[ConversationRead], summary="List conversations")
def list_conversations(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
    page_params: Annotated[PageParams, Depends()],
) -> PaginatedResponse[ConversationRead]:
    service = ConversationService(db)
    conversations, total = service.list_conversations(
        current_tenant.id, skip=page_params.offset, limit=page_params.per_page
    )
    items = [ConversationRead.model_validate(c) for c in conversations]
    return page_params.make_response(items, total)


@router.get("/{conversation_id}", response_model=ConversationRead, summary="Get conversation")
def get_conversation(
    conversation_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationRead:
    service = ConversationService(db)
    return service.get_conversation(current_tenant.id, conversation_id)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add dialogue turn message",
)
def add_message(
    conversation_id: uuid.UUID,
    data: MessageCreate,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> MessageRead:
    service = ConversationService(db)
    return service.add_message(current_tenant.id, conversation_id, data)


@router.get("/{conversation_id}/messages", response_model=list[MessageRead], summary="List conversation messages")
def list_messages(
    conversation_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> Sequence[MessageRead]:
    service = ConversationService(db)
    return service.list_messages(current_tenant.id, conversation_id)
