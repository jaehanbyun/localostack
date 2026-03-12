from fastapi import FastAPI


def create_glance_app() -> FastAPI:
    app = FastAPI(
        title="LocalOStack Glance",
        description="Image Service API v2",
        version="2.0",
    )

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
