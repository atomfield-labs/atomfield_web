"""
Standard API router aggregation.
Assembles all domain routers under a unified /api prefix.
"""

from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.files import router as files_router
from app.api.routes.jobs import router as jobs_router
from app.api.routes.mock import router as mock_router
from app.api.routes.scripts import router as scripts_router

api_router = APIRouter(prefix="/api")

api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(jobs_router)
api_router.include_router(files_router)
api_router.include_router(scripts_router)
api_router.include_router(mock_router)

__all__ = ["api_router"]
