"""
Standard API router aggregation.
Assembles all domain routers under a unified /api prefix.
"""

from fastapi import APIRouter

from app.agents.routes import router as agents_router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.catalog import router as catalog_router
from app.api.routes.files import router as files_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.mock import router as mock_router
from app.api.routes.runs import router as runs_router
from app.api.routes.storage import router as storage_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(agents_router)
api_router.include_router(catalog_router)
api_router.include_router(jobs_router)
api_router.include_router(runs_router)
api_router.include_router(files_router)
api_router.include_router(storage_router)
api_router.include_router(mock_router)

__all__ = ["api_router"]
