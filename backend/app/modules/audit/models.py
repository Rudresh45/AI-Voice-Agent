"""Audit domain models."""

from app.db.models import AuditEvent, AuditOutcome

__all__ = ["AuditEvent", "AuditOutcome"]
