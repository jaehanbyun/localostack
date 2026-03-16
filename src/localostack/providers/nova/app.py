"""Nova (Compute Service) app factory."""

from fastapi import FastAPI, Request

from localostack.core.config import load_config

from .routes import router, _AuthError
from .store import NovaStore

NOVA_MIN_MICROVERSION = "2.1"
NOVA_MAX_MICROVERSION = "2.47"


def _parse_microversion(request: Request) -> str:
    """Return negotiated Nova microversion, clamped to [min, max]."""
    header = request.headers.get("X-OpenStack-Nova-API-Version", "")
    if not header:
        oai = request.headers.get("OpenStack-API-Version", "")
        if oai.startswith("compute "):
            header = oai[len("compute "):].strip()

    if not header:
        return NOVA_MIN_MICROVERSION
    if header == "latest":
        return NOVA_MAX_MICROVERSION

    try:
        req = tuple(int(x) for x in header.split("."))
        min_v = tuple(int(x) for x in NOVA_MIN_MICROVERSION.split("."))
        max_v = tuple(int(x) for x in NOVA_MAX_MICROVERSION.split("."))
        if req < min_v:
            return NOVA_MIN_MICROVERSION
        if req > max_v:
            return NOVA_MAX_MICROVERSION
        return header
    except ValueError:
        return NOVA_MIN_MICROVERSION


def create_nova_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Nova",
        description="Compute Service API v2.1",
        version="2.1",
    )

    config = load_config()

    store = NovaStore(backend=backend)
    store.bootstrap()
    app.state.nova_store = store
    app.state.nova_config = config

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    @app.middleware("http")
    async def add_microversion_headers(request, call_next):
        mv = _parse_microversion(request)
        request.state.nova_microversion = mv
        response = await call_next(request)
        response.headers["X-OpenStack-Nova-API-Version"] = mv
        response.headers["OpenStack-API-Version"] = f"compute {mv}"
        response.headers["Vary"] = "X-OpenStack-Nova-API-Version, OpenStack-API-Version"
        return response

    if fault_registry is not None:
        _fr = fault_registry  # capture in closure
        _svc = "nova"         # service name string

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
                    "id": "v2.1",
                    "status": "CURRENT",
                    "version": NOVA_MAX_MICROVERSION,
                    "min_version": NOVA_MIN_MICROVERSION,
                    "links": [{"rel": "self", "href": f"{base}/v2.1/"}],
                }
            ]
        }

    @app.get("/v2.1")
    @app.get("/v2.1/")
    async def v21_root(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "version": {
                "id": "v2.1",
                "status": "CURRENT",
                "version": NOVA_MAX_MICROVERSION,
                "min_version": NOVA_MIN_MICROVERSION,
                "links": [{"rel": "self", "href": f"{base}/v2.1/"}],
            }
        }

    return app
