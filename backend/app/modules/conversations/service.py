"""Conversations domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.core.errors import EntityNotFoundError
from app.modules.conversations.models import Conversation
from app.modules.conversations.repository import ConversationDomainRepository
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationRead,
    MessageCreate,
    MessageRead,
)


class ConversationService:
    """Business operations for dialogues and turns."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ConversationDomainRepository(db)

    def create_conversation(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, data: ConversationCreate
    ) -> ConversationRead:
        conv = self.repo.create(
            tenant_id=tenant_id,
            agent_id=data.agent_id,
            user_id=user_id,
            title=data.title or "New Conversation",
        )
        self.db.commit()
        return ConversationRead.model_validate(conv)

    def get_conversation(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> ConversationRead:
        conv = self.repo.get_with_messages(conversation_id, tenant_id)
        if conv is None:
            raise EntityNotFoundError("Conversation", conversation_id)
        return ConversationRead.model_validate(conv)

    def list_conversations(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[Conversation], int]:
        total = self.repo.count_by_tenant(tenant_id)
        conversations = self.repo.list_paginated(tenant_id, skip=skip, limit=limit)
        return conversations, total

    def add_message(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID, data: MessageCreate
    ) -> MessageRead:
        msg = self.repo.add_message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role=data.role,
            content=data.content,
            token_count=data.token_count,
            meta_data=data.meta_data,
        )
        self.db.commit()
        return MessageRead.model_validate(msg)

    def list_messages(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Sequence[MessageRead]:
        messages = self.repo.get_messages_ordered(tenant_id, conversation_id)
        return [MessageRead.model_validate(m) for m in messages]
