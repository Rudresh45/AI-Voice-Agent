"""Knowledge domain service."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.modules.knowledge.models import KnowledgeDocument
from app.modules.knowledge.repository import KnowledgeRepository
from app.modules.knowledge.schemas import DocumentCreate, DocumentRead


class KnowledgeService:
    """Business operations for knowledge document registration."""

    def __init__(self, db: Session):
        self.db = db
        self.repo = KnowledgeRepository(db)

    def register_document(self, tenant_id: uuid.UUID, data: DocumentCreate) -> DocumentRead:
        doc = KnowledgeDocument(
            tenant_id=tenant_id,
            title=data.title,
            storage_key=data.storage_key,
            content_type=data.content_type,
            byte_size=data.byte_size,
            checksum_sha256=data.checksum_sha256,
            meta_data=data.meta_data,
        )
        self.db.add(doc)
        self.db.commit()
        self.db.refresh(doc)
        return DocumentRead.model_validate(doc)

    def get_document(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> DocumentRead:
        doc = self.repo.get_by_id_scoped(document_id, tenant_id)
        return DocumentRead.model_validate(doc)

    def list_documents(
        self, tenant_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> tuple[Sequence[KnowledgeDocument], int]:
        total = self.repo.count_by_tenant(tenant_id)
        docs = self.repo.list_paginated(tenant_id, skip=skip, limit=limit)
        return docs, total

    def delete_document(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> None:
        self.repo.delete_scoped(document_id, tenant_id)
        self.db.commit()
