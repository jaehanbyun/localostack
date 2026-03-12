"""Placement API app factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .routes import router, PLACEMENT_VERSION, PLACEMENT_MIN_VERSION
from .store import PlacementStore


def create_placement_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Placement",
        description="Resource Provider API",
        version="1.0",
    )

    store = PlacementStore(backend=backend)
    store.bootstrap()
    app.state.placement_store = store

    app.include_router(router)

    @app.middleware("http")
    async def add_placement_headers(request, call_next):
        response = await call_next(request)
        response.headers["OpenStack-API-Version"] = f"placement {PLACEMENT_VERSION}"
        response.headers["X-OpenStack-Request-ID"] = "req-localostack"
        response.headers["Vary"] = "OpenStack-API-Version"
        return response

    if fault_registry is not None:
        _fr = fault_registry

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, "placement")(request, call_next)

    return app
