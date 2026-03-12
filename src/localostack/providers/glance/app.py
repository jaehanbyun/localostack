from fastapi import FastAPI, Request

from localostack.core.config import load_config
from .routes import router, _AuthError
from .store import GlanceStore


def create_glance_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Glance",
        description="Image Service API v2",
        version="2.0",
    )

    config = load_config()

    store = GlanceStore()
    store.bootstrap(admin_project_id=config.admin_project)
    app.state.glance_store = store

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    @app.get("/")
    async def version_discovery():
        return {
            "versions": [
                {
                    "id": "v2.0",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": "/v2/"}],
                }
            ]
        }

    return app
