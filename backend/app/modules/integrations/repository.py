"""Integrations domain repository."""

from sqlalchemy.orm import Session

from app.db.repositories.agent import ToolRepository


class IntegrationsRepository(ToolRepository):
    """Repository managing tool definitions and integration links."""

    def __init__(self, db: Session):
        super().__init__(db)
