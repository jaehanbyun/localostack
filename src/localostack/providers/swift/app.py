"""Swift Object Storage app factory."""

from __future__ import annotations

from fastapi import FastAPI

from .routes import router
from .store import SwiftStore

SWIFT_VERSION = "1.0"


def create_swift_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Swift",
        description="Object Storage Service API",
        version=SWIFT_VERSION,
    )

    store = SwiftStore(backend=backend)
    store.bootstrap()
    app.state.swift_store = store

    app.include_router(router)

    if fault_registry is not None:
        _fr = fault_registry

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, "swift")(request, call_next)

    return app
