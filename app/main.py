from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.activity.router import router as activity_router
from app.activity.seed import seed_activity
from app.api.v1 import api_router
from app.auth.seed import seed_users
from app.core.errors import register_exception_handlers
from app.notifications.router import router as notifications_router
from app.notifications.seed import seed_notifications

app = FastAPI(
    title="Simo OS",
    version="0.1.0",
    description="AI Operating System"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

# Sprint 003: every route below (except / and /health, which stay
# unversioned as infra/health-check endpoints) is mounted under /api/v1
# (ADR-012). activity/notifications keep their own router.py untouched
# (ADR-002) — the prefix is applied here, at mount time.
app.include_router(api_router)
app.include_router(activity_router, prefix="/api/v1")
app.include_router(notifications_router, prefix="/api/v1")

seed_activity()
seed_notifications()
seed_users()


@app.get("/")
def root():
    return {
        "message": "Welcome to Simo OS",
        "status": "running"
    }


@app.get("/health")
def health():
    return {
        "status": "healthy"
    }
