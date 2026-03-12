"""Heat (Orchestration) API app factory."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router
from .store import HeatStore

HEAT_VERSION = "1.0"


def create_heat_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Heat",
        description="Orchestration Service API",
        version=HEAT_VERSION,
    )

    store = HeatStore(backend=backend)
    app.state.heat_store = store

    @app.get("/")
    async def version_discovery():
        return {
            "versions": [
                {
                    "id": "v1.0",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": "/v1"}],
                }
            ]
        }

    app.include_router(router)

    @app.middleware("http")
    async def add_heat_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-OpenStack-Request-ID"] = "req-localostack"
        return response

    if fault_registry is not None:
        _fr = fault_registry

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, "heat")(request, call_next)

    return app
