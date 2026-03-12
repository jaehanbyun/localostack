from fastapi import FastAPI, Request

from localostack.core.config import load_config
from .routes import router, _AuthError
from .store import NeutronStore


def create_neutron_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Neutron",
        description="Networking Service API v2.0",
        version="2.0",
    )

    config = load_config()

    store = NeutronStore()
    store.bootstrap(admin_project_id=config.admin_project)
    app.state.neutron_store = store

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
                    "links": [{"rel": "self", "href": "/v2.0/"}],
                }
            ]
        }

    return app
