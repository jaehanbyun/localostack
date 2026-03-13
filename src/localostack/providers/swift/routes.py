"""Swift Object Storage API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .store import SwiftStore

router = APIRouter()


def _get_store(request: Request) -> SwiftStore:
    return request.app.state.swift_store


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        return None
    return token_id


# ── Capabilities ──────────────────────────────────────────────────────

@router.get("/")
async def version_discovery(request: Request):
    base = str(request.base_url).rstrip("/")
    return {"versions": [{"id": "v1", "status": "CURRENT", "links": [{"rel": "self", "href": f"{base}/v1/"}]}]}


@router.get("/info")
async def swift_info():
    return {"swift": {"version": "1.0"}, "bulk_delete": {}, "bulk_upload": {}}


# ── Account ───────────────────────────────────────────────────────────

@router.get("/v1/{account}")
async def account_info(account: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    info = store.account_info(account)
    containers = store.list_containers(account)
    container_list = [
        {
            "name": c.name,
            "count": len(store.list_objects(account, c.name)),
            "bytes": sum(o.size for o in store.list_objects(account, c.name)),
            "last_modified": c.created_at,
        }
        for c in containers
    ]
    return JSONResponse(
        content=container_list,
        headers={
            "X-Account-Container-Count": str(info["container_count"]),
            "X-Account-Object-Count": str(info["object_count"]),
            "X-Account-Bytes-Used": str(info["bytes_used"]),
        },
    )


# ── Container ─────────────────────────────────────────────────────────

@router.put("/v1/{account}/{container}")
async def create_container(account: str, container: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    _, created = store.create_container(account, container)
    return Response(status_code=201 if created else 202)


@router.get("/v1/{account}/{container}")
async def list_objects(account: str, container: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    if store.get_container(account, container) is None:
        return Response(status_code=404)
    objects = store.list_objects(account, container)
    obj_list = [
        {
            "name": o.name,
            "bytes": o.size,
            "content_type": o.content_type,
            "hash": o.etag,
            "last_modified": o.last_modified,
        }
        for o in objects
    ]
    return JSONResponse(
        content=obj_list,
        headers={
            "X-Container-Object-Count": str(len(objects)),
            "X-Container-Bytes-Used": str(sum(o.size for o in objects)),
        },
    )


@router.head("/v1/{account}/{container}")
async def head_container(account: str, container: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    if store.get_container(account, container) is None:
        return Response(status_code=404)
    objects = store.list_objects(account, container)
    return Response(
        status_code=204,
        headers={
            "X-Container-Object-Count": str(len(objects)),
            "X-Container-Bytes-Used": str(sum(o.size for o in objects)),
        },
    )


@router.delete("/v1/{account}/{container}")
async def delete_container(account: str, container: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    result = store.delete_container(account, container)
    if result == "not_found":
        return Response(status_code=404)
    if result == "not_empty":
        return Response(status_code=409, content="Container not empty")
    return Response(status_code=204)


# ── Object ────────────────────────────────────────────────────────────

@router.put("/v1/{account}/{container}/{object_name:path}")
async def put_object(account: str, container: str, object_name: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    if store.get_container(account, container) is None:
        return Response(status_code=404, content="Container not found")
    content_type = request.headers.get("Content-Type", "application/octet-stream")
    data = await request.body()
    obj = store.put_object(account, container, object_name, data, content_type)
    return Response(
        status_code=201,
        headers={"ETag": obj.etag, "Last-Modified": obj.last_modified},
    )


@router.get("/v1/{account}/{container}/{object_name:path}")
async def get_object(account: str, container: str, object_name: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    obj = store.get_object(account, container, object_name)
    if obj is None:
        return Response(status_code=404)
    return Response(
        content=obj.content,
        media_type=obj.content_type,
        headers={
            "Content-Length": str(obj.size),
            "ETag": obj.etag,
            "Last-Modified": obj.last_modified,
        },
    )


@router.head("/v1/{account}/{container}/{object_name:path}")
async def head_object(account: str, container: str, object_name: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    obj = store.get_object(account, container, object_name)
    if obj is None:
        return Response(status_code=404)
    return Response(
        status_code=200,
        headers={
            "Content-Length": str(obj.size),
            "Content-Type": obj.content_type,
            "ETag": obj.etag,
            "Last-Modified": obj.last_modified,
        },
    )


@router.delete("/v1/{account}/{container}/{object_name:path}")
async def delete_object(account: str, container: str, object_name: str, request: Request):
    token = _require_token(request)
    if not token:
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_object(account, container, object_name):
        return Response(status_code=404)
    return Response(status_code=204)
