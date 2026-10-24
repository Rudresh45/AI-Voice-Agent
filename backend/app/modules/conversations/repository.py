"""Conversations domain repository."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, Message
from app.db.repositories.conversation import ConversationRepository


class ConversationDomainRepository(ConversationRepository):
    """Domain-specific repository extending standard ConversationRepository."""

    def count_by_tenant(self, tenant_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Conversation).where(Conversation.tenant_id == tenant_id)
        return self.db.scalar(stmt) or 0

    def list_paginated(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> Sequence[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.tenant_id == tenant_id)
            .options(selectinload(Conversation.messages))
            .order_by(Conversation.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return self.db.scalars(stmt).all()

    def get_messages_ordered(
        self, tenant_id: uuid.UUID, conversation_id: uuid.UUID
    ) -> Sequence[Message]:
        # Assert tenant isolation first
        self.get_by_id_scoped(conversation_id, tenant_id)
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.tenant_id == tenant_id,
            )
            .order_by(Message.created_at.asc())
        )
        return self.db.scalars(stmt).all()
