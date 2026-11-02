"""
Standard API router aggregation.
Assembles all domain routers under a unified /api prefix.
"""

from fastapi import APIRouter

from app.agents.routes import router as agents_router
from app.api.routes.admin import router as admin_router
from app.api.routes.ai import router as ai_router
from app.api.routes.auth import router as auth_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.data_packs import router as data_packs_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.labs import router as labs_router
from app.api.routes.pairings import agent_router as pairing_agent_router
from app.api.routes.pairings import router as pairings_router
from app.api.routes.releases import router as releases_router
from app.api.routes.runs import router as runs_router
from app.api.routes.script_keys import router as script_keys_router
from app.api.routes.sessions import router as sessions_router
from app.api.routes.storage import router as storage_router
from app.api.routes.targets import router as targets_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(script_keys_router)
api_router.include_router(admin_router)
api_router.include_router(ai_router)
api_router.include_router(agents_router)
api_router.include_router(pairing_agent_router)
api_router.include_router(pairings_router)
api_router.include_router(catalog_router)
api_router.include_router(releases_router)
api_router.include_router(data_packs_router)
api_router.include_router(jobs_router)
api_router.include_router(labs_router)
api_router.include_router(runs_router)
api_router.include_router(sessions_router)
api_router.include_router(storage_router)
api_router.include_router(targets_router)

__all__ = ["api_router"]
