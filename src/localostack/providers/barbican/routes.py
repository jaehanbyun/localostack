"""Barbican Key Manager API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from .store import BarbicanStore

router = APIRouter()


def _get_store(request: Request) -> BarbicanStore:
    return request.app.state.barbican_store


def _require_token(request: Request) -> str | None:
    return request.headers.get("X-Auth-Token")


def _secret_ref(request: Request, secret_id: str) -> str:
    host = request.headers.get("host", "localhost")
    scheme = "http"
    return f"{scheme}://{host}/v1/secrets/{secret_id}"


def _secret_detail(s, request: Request) -> dict:
    return {
        "secret_ref": _secret_ref(request, s.id),
        "name": s.name,
        "algorithm": s.algorithm,
        "bit_length": s.bit_length,
        "mode": s.mode,
        "payload_content_type": s.payload_content_type,
        "status": s.status,
        "created": s.created,
        "updated": s.updated,
        "secret_type": s.secret_type,
        "expiration": s.expiration,
    }


@router.get("/")
async def version_discovery():
    return {"versions": {"values": [{"id": "v1", "status": "stable", "links": [{"rel": "self", "href": "/v1"}]}]}}


@router.get("/v1/secrets")
async def list_secrets(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    secrets = store.list_secrets()
    return {
        "secrets": [_secret_detail(s, request) for s in secrets],
        "total": len(secrets),
        "next": None,
        "previous": None,
    }


@router.post("/v1/secrets", status_code=201)
async def create_secret(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    s = store.create_secret(
        name=body.get("name", ""),
        payload=body.get("payload", ""),
        payload_content_type=body.get("payload_content_type", "text/plain"),
        algorithm=body.get("algorithm", ""),
        bit_length=body.get("bit_length", 0),
        mode=body.get("mode", ""),
        secret_type=body.get("secret_type", "opaque"),
        expiration=body.get("expiration"),
    )
    return JSONResponse(
        status_code=201,
        content={"secret_ref": _secret_ref(request, s.id)},
    )


@router.get("/v1/secrets/{secret_id}")
async def get_secret(secret_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    s = store.get_secret(secret_id)
    if s is None:
        return Response(status_code=404)
    return _secret_detail(s, request)


@router.get("/v1/secrets/{secret_id}/payload")
async def get_secret_payload(secret_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    s = store.get_secret(secret_id)
    if s is None:
        return Response(status_code=404)
    return PlainTextResponse(content=s.payload, media_type=s.payload_content_type)


@router.delete("/v1/secrets/{secret_id}")
async def delete_secret(secret_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_secret(secret_id):
        return Response(status_code=404)
    return Response(status_code=204)
