"""Nova (Compute Service) app factory."""

from fastapi import FastAPI, Request

from localostack.core.config import load_config

from .routes import router, _AuthError
from .store import NovaStore


def create_nova_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Nova",
        description="Compute Service API v2.1",
        version="2.1",
    )

    config = load_config()

    store = NovaStore()
    store.bootstrap()
    app.state.nova_store = store
    app.state.nova_config = config

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    @app.middleware("http")
    async def add_microversion_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-OpenStack-Nova-API-Version"] = "2.1"
        response.headers["OpenStack-API-Version"] = "compute 2.1"
        response.headers["Vary"] = "X-OpenStack-Nova-API-Version, OpenStack-API-Version"
        return response

    @app.get("/")
    async def version_discovery():
        return {
            "versions": [
                {
                    "id": "v2.1",
                    "status": "CURRENT",
                    "version": "2.1",
                    "min_version": "2.1",
                    "links": [{"rel": "self", "href": "/v2.1/"}],
                }
            ]
        }

    return app
