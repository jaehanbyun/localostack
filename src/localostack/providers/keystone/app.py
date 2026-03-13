import os

from fastapi import FastAPI

from fastapi import Request

from localostack.core.config import load_config
from .routes import router, _AuthError
from .store import KeystoneStore


def create_keystone_app(backend=None, fault_registry=None) -> FastAPI:
    app = FastAPI(
        title="LocalOStack Keystone",
        description="Identity Service API v3",
        version="3.0",
    )

    config = load_config()
    endpoint_host = os.environ.get("LOCALOSTACK_ENDPOINT_HOST", "localhost")

    store = KeystoneStore(backend=backend)
    store.bootstrap(
        admin_username=config.admin_username,
        admin_password=config.admin_password,
        admin_project=config.admin_project,
        region=config.region,
        endpoint_host=endpoint_host,
        keystone_port=config.keystone_port,
        nova_port=config.nova_port,
        neutron_port=config.neutron_port,
        glance_port=config.glance_port,
        cinder_port=config.cinder_port,
        placement_port=config.placement_port,
        heat_port=config.heat_port,
        swift_port=config.swift_port,
        barbican_port=config.barbican_port,
        octavia_port=config.octavia_port,
    )
    app.state.keystone_store = store

    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def auth_error_handler(request: Request, exc: _AuthError):
        return exc.response

    if fault_registry is not None:
        _fr = fault_registry  # capture in closure
        _svc = "keystone"     # service name string

        @app.middleware("http")
        async def _fault_mw(request, call_next):
            from localostack.core.fault_injection import make_fault_middleware
            return await make_fault_middleware(_fr, _svc)(request, call_next)

    @app.get("/")
    async def version_discovery(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "versions": {
                "values": [
                    {
                        "id": "v3.14",
                        "status": "stable",
                        "links": [{"rel": "self", "href": f"{base}/v3/"}],
                    }
                ]
            }
        }

    @app.get("/v3")
    async def v3_root(request: Request):
        base = str(request.base_url).rstrip("/")
        return {
            "version": {
                "id": "v3.14",
                "status": "stable",
                "links": [{"rel": "self", "href": f"{base}/v3/"}],
            }
        }

    return app
