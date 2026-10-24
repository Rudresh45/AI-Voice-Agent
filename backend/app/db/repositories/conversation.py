"""Conversation, Message, and ToolExecution repositories."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Conversation,
    ConversationStatus,
    Message,
    ToolExecution,
    ToolExecutionStatus,
)
from app.db.repositories.base import TenantScopedRepository


class ConversationRepository(TenantScopedRepository[Conversation]):
    """Repository managing dialogue sessions, messages, and tool executions."""

    def __init__(self, db: Session):
        super().__init__(Conversation, db)

    def create(
        self,
        tenant_id: uuid.UUID,
        agent_id: uuid.UUID,
        user_id: uuid.UUID | None = None,
        title: str | None = None,
    ) -> Conversation:
        conversation = Conversation(
            tenant_id=tenant_id,
            agent_id=agent_id,
            user_id=user_id,
            title=title,
            status=ConversationStatus.ACTIVE.value,
        )
        return self.add(conversation)

    def get_with_messages(
        self, conversation_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> Conversation | None:
        """Fetch conversation enforcing tenant isolation with messages ordered by created_at."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
            .options(selectinload(Conversation.messages))
        )
        return self.db.scalars(stmt).first()

    def add_message(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        role: str,
        content: str,
        token_count: int | None = None,
        meta_data: dict[str, Any] | None = None,
    ) -> Message:
        """Append an authorized message to a conversation."""
        # Verify conversation belongs to tenant
        self.get_by_id_scoped(conversation_id, tenant_id)

        msg = Message(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
            meta_data=meta_data or {},
        )
        self.db.add(msg)
        self.db.flush()
        return msg

    def record_tool_execution(
        self,
        tenant_id: uuid.UUID,
        conversation_id: uuid.UUID,
        tool_name: str,
        arguments_json: dict[str, Any],
        tool_id: uuid.UUID | None = None,
        idempotency_key: str | None = None,
        status: str = ToolExecutionStatus.PROPOSED.value,
    ) -> ToolExecution:
        """Create an execution log for a proposed or authorized tool invocation."""
        # Verify conversation belongs to tenant
        self.get_by_id_scoped(conversation_id, tenant_id)

        execution = ToolExecution(
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            tool_id=tool_id,
            tool_name=tool_name,
            idempotency_key=idempotency_key,
            arguments_json=arguments_json,
            status=status,
        )
        self.db.add(execution)
        self.db.flush()
        return execution

    def complete_tool_execution(
        self,
        execution_id: uuid.UUID,
        tenant_id: uuid.UUID,
        result_json: dict[str, Any],
        duration_ms: int,
    ) -> ToolExecution:
        """Mark a tool execution as successfully completed."""
        stmt = select(ToolExecution).where(
            ToolExecution.id == execution_id, ToolExecution.tenant_id == tenant_id
        )
        execution = self.db.scalars(stmt).one()
        execution.status = ToolExecutionStatus.COMPLETED.value
        execution.result_json = result_json
        execution.duration_ms = duration_ms
        execution.completed_at = datetime.now()
        self.db.flush()
        return execution
