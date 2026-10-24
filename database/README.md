# Database

PostgreSQL is the system of record. Use Alembic migrations in the backend as the
canonical schema history. Suggested entities: tenants, users, memberships, agents,
tool definitions, agent-tool permissions, conversations, messages, tool executions,
knowledge documents, usage events, audit events and outbox events.

Every tenant-owned row must be tenant-scoped. Use foreign keys, indexes, UTC
timestamps, least-privilege roles, tested migrations and backup/restore drills.
