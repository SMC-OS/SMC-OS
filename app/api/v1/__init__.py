"""Assembles every /api/v1 route (ADR-012) into one router main.py mounts.

app/activity and app/notifications keep their own router.py files unchanged
(per ADR-002's "don't touch existing route bodies" spirit) — the /api/v1
prefix is applied to them at include_router() time in main.py, not here.
"""

from fastapi import APIRouter

from app.ai.router import router as ai_router
from app.api.v1.core import router as core_router
from app.appointments.router import router as appointments_router
from app.automations.router import router as automations_router
from app.auth.router import router as auth_router
from app.calendar.router import router as calendar_router
from app.billing.router import router as billing_router
from app.catalogue.router import router as catalogue_router
from app.communications.router import router as communications_router
from app.customers.router import router as customers_router
from app.dashboard.router import router as dashboard_router
from app.demo_requests.router import router as demo_requests_router
from app.documents.router import router as documents_router
from app.financials.router import router as financials_router
from app.procurement.router import router as procurement_router
from app.invitations.router import router as invitations_router
from app.messages.router import router as messages_router
from app.portal.router import router as portal_router
from app.projects.router import router as projects_router
from app.quotes.router import router as quotes_router
from app.tasks.router import router as tasks_router
from app.tenants.router import router as tenants_router
from app.users.router import router as users_router
from app.variations.router import router as variations_router
from app.workflows.router import router as workflows_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(core_router)
api_router.include_router(ai_router)
api_router.include_router(appointments_router)
api_router.include_router(automations_router)
api_router.include_router(auth_router)
api_router.include_router(billing_router)
api_router.include_router(calendar_router)
api_router.include_router(catalogue_router)
api_router.include_router(communications_router)
api_router.include_router(customers_router)
api_router.include_router(dashboard_router)
api_router.include_router(demo_requests_router)
api_router.include_router(documents_router)
api_router.include_router(financials_router)
api_router.include_router(invitations_router)
api_router.include_router(messages_router)
api_router.include_router(portal_router)
api_router.include_router(procurement_router)
api_router.include_router(projects_router)
api_router.include_router(quotes_router)
api_router.include_router(tasks_router)
api_router.include_router(tenants_router)
api_router.include_router(users_router)
api_router.include_router(variations_router)
api_router.include_router(workflows_router)
