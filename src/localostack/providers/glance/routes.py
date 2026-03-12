from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .models import ImageCreateRequest, ImageUpdateRequest
from .store import GlanceStore

router = APIRouter()


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": {"message": message, "code": code}},
    )


def _get_store(request: Request) -> GlanceStore:
    return request.app.state.glance_store


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        raise _AuthError(_error(401, "Authentication required"))
    return token_id


class _AuthError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


def _image_to_dict(img) -> dict:
    return {
        "id": img.id,
        "name": img.name,
        "status": img.status,
        "visibility": img.visibility,
        "container_format": img.container_format,
        "disk_format": img.disk_format,
        "min_disk": img.min_disk,
        "min_ram": img.min_ram,
        "size": img.size,
        "checksum": img.checksum,
        "owner": img.owner,
        "created_at": img.created_at,
        "updated_at": img.updated_at,
        "tags": img.tags,
        "self": f"/v2/images/{img.id}",
        "file": f"/v2/images/{img.id}/file",
        "schema": "/v2/schemas/image",
    }


# ── Image CRUD ──────────────────────────────────────────────

@router.get("/v2/images")
async def list_images(request: Request):
    _require_token(request)
    store = _get_store(request)
    visibility = request.query_params.get("visibility")
    images = store.list_images(visibility=visibility)
    return {
        "images": [_image_to_dict(img) for img in images],
        "schema": "/v2/schemas/images",
        "first": "/v2/images",
    }


@router.post("/v2/images", status_code=201)
async def create_image(body: ImageCreateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    image = store.create_image(
        name=body.name,
        container_format=body.container_format,
        disk_format=body.disk_format,
        visibility=body.visibility,
        min_disk=body.min_disk,
        min_ram=body.min_ram,
        tags=body.tags,
        properties=body.properties,
    )
    return JSONResponse(status_code=201, content=_image_to_dict(image))


@router.get("/v2/images/{image_id}")
async def get_image(image_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    image = store.get_image(image_id)
    if image is None:
        return _error(404, "Image not found")
    return _image_to_dict(image)


@router.patch("/v2/images/{image_id}")
async def update_image(image_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    image = store.get_image(image_id)
    if image is None:
        return _error(404, "Image not found")
    body = await request.json()
    updates = {}
    for key in ("name", "container_format", "disk_format", "visibility", "min_disk", "min_ram", "tags"):
        if key in body:
            updates[key] = body[key]
    image = store.update_image(image_id, **updates)
    return _image_to_dict(image)


@router.delete("/v2/images/{image_id}")
async def delete_image(image_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_image(image_id):
        return _error(404, "Image not found")
    return Response(status_code=204)


# ── Image File ──────────────────────────────────────────────

@router.put("/v2/images/{image_id}/file", status_code=204)
async def upload_file(image_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    data = await request.body()
    image = store.upload_file(image_id, data)
    if image is None:
        return _error(404, "Image not found")
    return Response(status_code=204)


@router.get("/v2/images/{image_id}/file")
async def download_file(image_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    image = store.get_image(image_id)
    if image is None:
        return _error(404, "Image not found")
    data = store.download_file(image_id)
    if data is None:
        return _error(204, "No image data")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-MD5": image.checksum or ""},
    )


# ── Image Tags ──────────────────────────────────────────────

@router.put("/v2/images/{image_id}/tags/{tag}", status_code=204)
async def add_tag(image_id: str, tag: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    image = store.add_tag(image_id, tag)
    if image is None:
        return _error(404, "Image not found")
    return Response(status_code=204)


@router.delete("/v2/images/{image_id}/tags/{tag}", status_code=204)
async def delete_tag(image_id: str, tag: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_tag(image_id, tag):
        return _error(404, "Image or tag not found")
    return Response(status_code=204)


# ── Schemas ─────────────────────────────────────────────────

@router.get("/v2/schemas/images")
async def images_schema():
    return {
        "name": "images",
        "properties": {
            "images": {"items": {"$ref": "/v2/schemas/image"}, "type": "array"},
            "schema": {"type": "string"},
            "first": {"type": "string"},
            "next": {"type": "string"},
        },
    }


@router.get("/v2/schemas/image")
async def image_schema():
    return {
        "name": "image",
        "properties": {
            "id": {"type": "string", "description": "Image ID"},
            "name": {"type": "string", "description": "Image name"},
            "status": {"type": "string", "enum": ["queued", "saving", "active", "killed", "deleted", "pending_delete", "deactivated"]},
            "visibility": {"type": "string", "enum": ["public", "private", "shared", "community"]},
            "container_format": {"type": "string", "enum": ["bare", "ovf", "aki", "ari", "ami", "ova", "docker"]},
            "disk_format": {"type": "string", "enum": ["raw", "vhd", "vhdx", "vmdk", "vdi", "iso", "qcow2", "aki", "ari", "ami", "ploop"]},
            "min_disk": {"type": "integer"},
            "min_ram": {"type": "integer"},
            "size": {"type": ["integer", "null"]},
            "checksum": {"type": ["string", "null"]},
            "owner": {"type": "string"},
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "self": {"type": "string"},
            "file": {"type": "string"},
            "schema": {"type": "string"},
        },
    }
