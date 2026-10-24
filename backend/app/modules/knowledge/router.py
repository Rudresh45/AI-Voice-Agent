"""Knowledge domain API router with RBAC enforcement."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import (
    RequestContext,
    get_current_tenant,
    get_db,
    require_admin_access,
    require_write_access,
)
from app.core.pagination import PageParams, PaginatedResponse
from app.db.models import Tenant
from app.modules.knowledge.schemas import DocumentCreate, DocumentRead
from app.modules.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge"])


@router.post("/", response_model=DocumentRead, status_code=status.HTTP_201_CREATED, summary="Register document")
def register_document(
    data: DocumentCreate,
    context: Annotated[RequestContext, Depends(require_write_access)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentRead:
    service = KnowledgeService(db)
    return service.register_document(context.tenant.id, data)


@router.get("/", response_model=PaginatedResponse[DocumentRead], summary="List documents")
def list_documents(
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
    page_params: Annotated[PageParams, Depends()],
) -> PaginatedResponse[DocumentRead]:
    service = KnowledgeService(db)
    docs, total = service.list_documents(
        current_tenant.id, skip=page_params.offset, limit=page_params.per_page
    )
    items = [DocumentRead.model_validate(d) for d in docs]
    return page_params.make_response(items, total)


@router.get("/{document_id}", response_model=DocumentRead, summary="Get document")
def get_document(
    document_id: uuid.UUID,
    current_tenant: Annotated[Tenant, Depends(get_current_tenant)],
    db: Annotated[Session, Depends(get_db)],
) -> DocumentRead:
    service = KnowledgeService(db)
    return service.get_document(current_tenant.id, document_id)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete document")
def delete_document(
    document_id: uuid.UUID,
    context: Annotated[RequestContext, Depends(require_admin_access)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    service = KnowledgeService(db)
    service.delete_document(context.tenant.id, document_id)
