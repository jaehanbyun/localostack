from fastapi import FastAPI
from fastapi.responses import JSONResponse


def create_nova_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Nova",
        description="Compute Service API v2.1",
        version="2.1",
    )

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
