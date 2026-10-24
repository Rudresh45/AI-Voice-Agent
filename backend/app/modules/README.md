# Domain module pattern

Create one folder per domain: identity, tenants, agents, conversations, knowledge,
integrations, usage, billing, audit and platform_ops.

Each domain should contain:
- `models.py`: SQLAlchemy entities and constraints
- `schemas.py`: Pydantic request/response types
- `repository.py`: tenant-scoped persistence
- `service.py`: business rules and transaction boundaries
- `router.py`: thin FastAPI endpoints
- `tests/`: unit, integration and tenant-isolation tests

These domains are planned; do not assume they are implemented.
