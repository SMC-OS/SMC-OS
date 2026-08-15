"""Assembles every /api/v1 route (ADR-012) into one router main.py mounts.

app/activity and app/notifications keep their own router.py files unchanged
(per ADR-002's "don't touch existing route bodies" spirit) — the /api/v1
prefix is applied to them at include_router() time in main.py, not here.
"""

from fastapi import APIRouter

from app.api.v1.core import router as core_router
from app.auth.router import router as auth_router
from app.customers.router import router as customers_router
from app.invitations.router import router as invitations_router
from app.portal.router import router as portal_router
from app.projects.router import router as projects_router
from app.quotes.router import router as quotes_router
from app.tenants.router import router as tenants_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(core_router)
api_router.include_router(auth_router)
api_router.include_router(customers_router)
api_router.include_router(invitations_router)
api_router.include_router(portal_router)
api_router.include_router(projects_router)
api_router.include_router(quotes_router)
api_router.include_router(tenants_router)
