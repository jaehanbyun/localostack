"""Placement API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .store import PlacementStore

router = APIRouter()

PLACEMENT_VERSION = "1.39"
PLACEMENT_MIN_VERSION = "1.0"


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"errors": [{"status": code, "title": message}]})


def _get_store(request: Request) -> PlacementStore:
    return request.app.state.placement_store


def _require_token(request: Request) -> str:
    token = request.headers.get("X-Auth-Token")
    if not token:
        return _error(401, "Unauthorized")  # type: ignore
    return token


def _provider_to_dict(rp) -> dict:
    return {
        "uuid": rp.uuid,
        "name": rp.name,
        "generation": rp.generation,
        "parent_provider_uuid": rp.parent_provider_uuid,
        "root_provider_uuid": rp.parent_provider_uuid or rp.uuid,
        "links": [
            {"rel": "self", "href": f"/resource_providers/{rp.uuid}"},
            {"rel": "inventories", "href": f"/resource_providers/{rp.uuid}/inventories"},
            {"rel": "allocations", "href": f"/resource_providers/{rp.uuid}/allocations"},
        ],
    }


def _inventory_to_dict(inv) -> dict:
    return {
        "total": inv.total,
        "reserved": inv.reserved,
        "min_unit": inv.min_unit,
        "max_unit": inv.max_unit,
        "step_size": inv.step_size,
        "allocation_ratio": inv.allocation_ratio,
    }


# ── Version Discovery ──────────────────────────────────────

@router.get("/")
async def version_discovery():
    return {
        "versions": [
            {
                "id": "v1.0",
                "max_version": PLACEMENT_VERSION,
                "min_version": PLACEMENT_MIN_VERSION,
                "status": "CURRENT",
                "links": [{"rel": "self", "href": "/"}],
            }
        ]
    }


# ── Resource Providers ─────────────────────────────────────

@router.get("/resource_providers")
async def list_resource_providers(request: Request):
    _require_token(request)
    store = _get_store(request)
    name = request.query_params.get("name")
    providers = store.list_providers()
    if name:
        providers = [p for p in providers if p.name == name]
    return {"resource_providers": [_provider_to_dict(p) for p in providers]}


@router.post("/resource_providers", status_code=201)
async def create_resource_provider(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    rp = store.create_provider(
        name=body["name"],
        uuid=body.get("uuid"),
        parent_provider_uuid=body.get("parent_provider_uuid"),
    )
    return JSONResponse(status_code=201, content=_provider_to_dict(rp))


@router.get("/resource_providers/{rp_uuid}")
async def get_resource_provider(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    rp = store.get_provider(rp_uuid)
    if rp is None:
        return _error(404, "Resource provider not found")
    return _provider_to_dict(rp)


@router.delete("/resource_providers/{rp_uuid}")
async def delete_resource_provider(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_provider(rp_uuid):
        return _error(404, "Resource provider not found")
    return Response(status_code=204)


# ── Inventories ────────────────────────────────────────────

@router.get("/resource_providers/{rp_uuid}/inventories")
async def get_inventories(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    invs = store.get_inventories(rp_uuid)
    if invs is None:
        return _error(404, "Resource provider not found")
    rp = store.get_provider(rp_uuid)
    return {
        "inventories": {rc: _inventory_to_dict(inv) for rc, inv in invs.items()},
        "resource_provider_generation": rp.generation if rp else 0,
    }


@router.put("/resource_providers/{rp_uuid}/inventories")
async def set_inventories(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    inventories_data = body.get("inventories", {})
    result = store.set_inventories(rp_uuid, inventories_data)
    if result is None:
        return _error(404, "Resource provider not found")
    rp = store.get_provider(rp_uuid)
    return {
        "inventories": {rc: _inventory_to_dict(inv) for rc, inv in result.items()},
        "resource_provider_generation": rp.generation if rp else 0,
    }


@router.delete("/resource_providers/{rp_uuid}/inventories")
async def delete_inventories(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    result = store.set_inventories(rp_uuid, {})  # clear all
    if result is None:
        return _error(404, "Resource provider not found")
    return Response(status_code=204)


# ── Provider Allocations ───────────────────────────────────

@router.get("/resource_providers/{rp_uuid}/allocations")
async def get_provider_allocations(rp_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if store.get_provider(rp_uuid) is None:
        return _error(404, "Resource provider not found")
    allocs = store.get_provider_allocations(rp_uuid)
    # Group by consumer
    by_consumer: dict = {}
    for a in allocs:
        if a.consumer_uuid not in by_consumer:
            by_consumer[a.consumer_uuid] = {"resources": {}}
        by_consumer[a.consumer_uuid]["resources"][a.resource_class] = a.used
    return {
        "allocations": by_consumer,
        "resource_provider_generation": store.get_provider(rp_uuid).generation,
    }


# ── Consumer Allocations ───────────────────────────────────

@router.get("/allocations/{consumer_uuid}")
async def get_consumer_allocations(consumer_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    allocs = store.get_allocations_for_consumer(consumer_uuid)
    # Build response: {rp_uuid: {resources: {rc: amount}}}
    by_provider: dict = {}
    project_id = ""
    user_id = ""
    for alloc in allocs.values():
        if alloc.resource_provider_uuid not in by_provider:
            by_provider[alloc.resource_provider_uuid] = {"resources": {}}
        by_provider[alloc.resource_provider_uuid]["resources"][alloc.resource_class] = alloc.used
        project_id = alloc.project_id
        user_id = alloc.user_id
    return {
        "allocations": by_provider,
        "project_id": project_id,
        "user_id": user_id,
    }


@router.put("/allocations/{consumer_uuid}")
async def set_consumer_allocations(consumer_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    allocations = body.get("allocations", [])
    project_id = body.get("project_id", "")
    user_id = body.get("user_id", "")
    store.set_allocations(consumer_uuid, allocations, project_id=project_id, user_id=user_id)
    return Response(status_code=204)


@router.delete("/allocations/{consumer_uuid}")
async def delete_consumer_allocations(consumer_uuid: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    store.delete_allocations(consumer_uuid)  # idempotent — always 204
    return Response(status_code=204)


# ── Batch Allocations (POST /allocations) ─────────────────

@router.post("/allocations")
async def batch_set_allocations(request: Request):
    """Batch allocation endpoint (microversion 1.13+)."""
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    # body is {consumer_uuid: {"allocations": [...], "project_id": ..., "user_id": ...}}
    for consumer_uuid, data in body.items():
        allocations = data.get("allocations", [])
        project_id = data.get("project_id", "")
        user_id = data.get("user_id", "")
        store.set_allocations(consumer_uuid, allocations, project_id=project_id, user_id=user_id)
    return Response(status_code=204)


# ── Allocation Candidates ──────────────────────────────────

@router.get("/allocation_candidates")
async def get_allocation_candidates(request: Request):
    """Return our single resource provider as the only candidate."""
    _require_token(request)
    store = _get_store(request)
    params = request.query_params
    # Parse resources param: "VCPU:1,MEMORY_MB:512,DISK_GB:10"
    resources_str = params.get("resources", "")
    requested: dict[str, int] = {}
    for item in resources_str.split(","):
        if ":" in item:
            rc, amount = item.split(":", 1)
            try:
                requested[rc.strip()] = int(amount.strip())
            except ValueError:
                pass

    providers = store.list_providers()
    if not providers:
        return {"allocation_requests": [], "provider_summaries": {}}

    # Use the first (default) provider
    rp = providers[0]
    invs = store.get_inventories(rp.uuid) or {}

    # Build provider summary
    usage: dict[str, int] = {}
    for a in store.get_provider_allocations(rp.uuid):
        usage[a.resource_class] = usage.get(a.resource_class, 0) + a.used

    provider_summaries = {
        rp.uuid: {
            "resources": {
                rc: {
                    "capacity": int(inv.total * inv.allocation_ratio) - inv.reserved,
                    "used": usage.get(rc, 0),
                }
                for rc, inv in invs.items()
            },
            "traits": {"required": [], "forbidden": []},
        }
    }

    # Build allocation request
    allocation_request = {
        "allocations": {
            rp.uuid: {"resources": requested if requested else {rc: 1 for rc in invs}}
        }
    }

    return {
        "allocation_requests": [allocation_request],
        "provider_summaries": provider_summaries,
    }


# ── Usages ─────────────────────────────────────────────────

@router.get("/usages")
async def get_usages(request: Request):
    _require_token(request)
    store = _get_store(request)
    project_id = request.query_params.get("project_id")
    usage = store.get_usages(project_id=project_id)
    return {"usages": usage}
