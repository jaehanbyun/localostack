"""Cinder (Block Storage Service) app factory."""

from fastapi import FastAPI, Request

from .routes import router, _AuthError
from .store import CinderStore


def create_cinder_app(backend=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Cinder",
        description="Block Storage Service API v3",
        version="3.0",
    )

    store = CinderStore(backend=backend)
    store.bootstrap()
    app.state.cinder_store = store

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    @app.middleware("http")
    async def add_microversion_headers(request, call_next):
        response = await call_next(request)
        response.headers["OpenStack-Volume-microversion"] = "3.0"
        return response

    @app.get("/")
    async def version_discovery(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "versions": [
                {
                    "id": "v3.0",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": f"{base}/v3"}],
                }
            ]
        }

    @app.get("/v3")
    async def v3_root(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "version": {
                "id": "v3.0",
                "status": "CURRENT",
                "links": [{"rel": "self", "href": f"{base}/v3"}],
            }
        }

    return app
