"""Barbican Key Manager API app factory."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router
from .store import BarbicanStore

BARBICAN_VERSION = "1.0"


def create_barbican_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Barbican",
        description="Key Manager Service API",
        version=BARBICAN_VERSION,
    )

    store = BarbicanStore(backend=backend)
    store.bootstrap()
    app.state.barbican_store = store

    app.include_router(router)

    @app.middleware("http")
    async def add_barbican_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-OpenStack-Request-ID"] = "req-localostack"
        return response

    if fault_registry is not None:
        _fr = fault_registry

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, "barbican")(request, call_next)

    return app
