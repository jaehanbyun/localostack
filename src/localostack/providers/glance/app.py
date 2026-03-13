from fastapi import FastAPI, Request

from localostack.core.config import load_config
from .routes import router, _AuthError
from .store import GlanceStore


def create_glance_app(admin_project_id: str | None = None, backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Glance",
        description="Image Service API v2",
        version="2.0",
    )

    config = load_config()

    store = GlanceStore(backend=backend)
    store.bootstrap(admin_project_id=admin_project_id or config.admin_project)
    app.state.glance_store = store

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    if fault_registry is not None:
        _fr = fault_registry  # capture in closure
        _svc = "glance"       # service name string

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, _svc)(request, call_next)

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

    return app
