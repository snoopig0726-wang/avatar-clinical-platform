from fastapi import APIRouter

from app.api.routes import (
    adjustments,
    admin,
    auth,
    avatars,
    cases,
    features,
    health,
    invites,
    meta,
    sessions,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(cases.router, prefix="/cases", tags=["cases"])
api_router.include_router(invites.router, tags=["session-invites"])
api_router.include_router(sessions.router, tags=["sessions"])
api_router.include_router(features.router, tags=["voice-and-visual-features"])
api_router.include_router(avatars.router, tags=["avatar-generation"])
api_router.include_router(adjustments.router, tags=["adjustments-and-avatar-authorization"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
