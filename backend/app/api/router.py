"""Root API Router consolidating domain routers under /api/v1."""

from fastapi import APIRouter

from app.modules.agents.router import router as agents_router
from app.modules.audit.router import router as audit_router
from app.modules.conversations.router import router as conversations_router
from app.modules.identity.router import auth_router
from app.modules.identity.router import router as identity_router
from app.modules.integrations.router import router as integrations_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.platform_ops.router import router as platform_ops_router
from app.modules.tenants.router import router as tenants_router
from app.modules.usage.router import router as usage_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(identity_router)
api_router.include_router(tenants_router)
api_router.include_router(agents_router)
api_router.include_router(conversations_router)
api_router.include_router(knowledge_router)
api_router.include_router(integrations_router)
api_router.include_router(usage_router)
api_router.include_router(audit_router)
api_router.include_router(platform_ops_router)
