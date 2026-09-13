"""Version 1 of the API.

Versioned from the first endpoint so a breaking change later is a new prefix
rather than a coordinated frontend/backend release.
"""

from __future__ import annotations

from fastapi import APIRouter

from bsa.api.v1 import dashboard, imports, me, metrics, players, sync

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(me.router)
api_router.include_router(players.router)
api_router.include_router(metrics.router)
api_router.include_router(dashboard.router)
api_router.include_router(imports.router)
api_router.include_router(sync.router)

__all__ = ["api_router"]
