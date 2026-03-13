"""Octavia Load Balancer API app factory."""
from __future__ import annotations

from fastapi import FastAPI, Request

from .routes import router
from .store import OctaviaStore

OCTAVIA_VERSION = "2.0"


def create_octavia_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Octavia",
        description="Load Balancer Service API",
        version=OCTAVIA_VERSION,
    )

    store = OctaviaStore(backend=backend)
    store.bootstrap()
    app.state.octavia_store = store

    @app.get("/")
    async def version_discovery(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "versions": [
                {
                    "id": "v2.0",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": f"{base}/v2/"}],
                }
            ]
        }

    app.include_router(router)

    if fault_registry is not None:
        _fr = fault_registry

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, "octavia")(request, call_next)

    return app
