from fastapi import FastAPI


def create_neutron_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Neutron",
        description="Networking Service API v2.0",
        version="2.0",
    )

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
