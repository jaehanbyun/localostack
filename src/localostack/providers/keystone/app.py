from fastapi import FastAPI


def create_keystone_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Keystone",
        description="Identity Service API v3",
        version="3.0",
    )

    @app.get("/")
    async def version_discovery():
        return {
            "versions": {
                "values": [
                    {
                        "id": "v3.14",
                        "status": "stable",
                        "links": [{"rel": "self", "href": "/v3/"}],
                    }
                ]
            }
        }

    @app.get("/v3")
    async def v3_root():
        return {"version": {"id": "v3.14", "status": "stable"}}

    return app
