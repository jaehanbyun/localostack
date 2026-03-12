"""Heat (Orchestration) API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .store import HeatStore

router = APIRouter()

RESOURCE_TYPES = [
    "OS::Nova::Server",
    "OS::Neutron::Net",
    "OS::Neutron::Subnet",
    "OS::Neutron::Port",
    "OS::Neutron::SecurityGroup",
    "OS::Cinder::Volume",
    "OS::Glance::Image",
    "OS::Heat::Stack",
    "OS::Heat::WaitCondition",
    "OS::Heat::ResourceGroup",
    "OS::IAM::User",
]


def _get_store(request: Request) -> HeatStore:
    return request.app.state.heat_store


def _require_token(request: Request) -> str:
    token = request.headers.get("X-Auth-Token")
    if not token:
        return JSONResponse(status_code=401, content={"error": {"code": 401, "message": "Unauthorized"}})  # type: ignore
    return token


def _stack_summary(stack) -> dict:
    return {
        "id": stack.id,
        "stack_name": stack.name,
        "stack_status": stack.status,
        "creation_time": stack.created_at,
        "updated_time": stack.updated_at,
        "links": [{"rel": "self", "href": f"/v1/{stack.tenant_id}/stacks/{stack.name}/{stack.id}"}],
    }


def _stack_detail(stack) -> dict:
    return {
        "id": stack.id,
        "stack_name": stack.name,
        "stack_status": stack.status,
        "stack_status_reason": stack.status_reason,
        "parameters": stack.parameters,
        "outputs": list(stack.outputs.values()) if isinstance(stack.outputs, dict) else stack.outputs,
        "creation_time": stack.created_at,
        "updated_time": stack.updated_at,
        "tags": stack.tags,
        "links": [{"rel": "self", "href": f"/v1/{stack.tenant_id}/stacks/{stack.name}/{stack.id}"}],
    }


def _resource_dict(res: dict, tenant_id: str, stack_name: str, stack_id: str) -> dict:
    return {
        "resource_name": res.get("resource_name"),
        "resource_type": res.get("resource_type"),
        "resource_status": res.get("resource_status"),
        "physical_resource_id": res.get("physical_resource_id"),
        "logical_resource_id": res.get("logical_resource_id"),
        "links": [
            {"rel": "self", "href": f"/v1/{tenant_id}/stacks/{stack_name}/{stack_id}/resources/{res.get('resource_name')}"}
        ],
    }


# ── Resource Types ───────────────────────────────────────────

@router.get("/v1/{tenant_id}/resource_types")
async def list_resource_types(tenant_id: str, request: Request):
    _require_token(request)
    return {"resource_types": RESOURCE_TYPES}


# ── Stacks ───────────────────────────────────────────────────

@router.get("/v1/{tenant_id}/stacks")
async def list_stacks(tenant_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    stacks = store.list_stacks()
    visible = [s for s in stacks if s.status != "DELETE_COMPLETE"]
    return {"stacks": [_stack_summary(s) for s in visible]}


@router.post("/v1/{tenant_id}/stacks", status_code=201)
async def create_stack(tenant_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    name = body.get("stack_name", "")
    template = body.get("template") or {}
    parameters = body.get("parameters") or {}
    tags_raw = body.get("tags")
    tags = tags_raw if isinstance(tags_raw, list) else ([tags_raw] if tags_raw else [])
    stack = store.create_stack(
        name=name,
        template=template,
        parameters=parameters,
        tags=tags,
        tenant_id=tenant_id,
    )
    return JSONResponse(status_code=201, content={
        "stack": {
            "id": stack.id,
            "links": [{"rel": "self", "href": f"/v1/{tenant_id}/stacks/{stack.name}/{stack.id}"}],
        }
    })


@router.get("/v1/{tenant_id}/stacks/{stack_name}/{stack_id}")
async def get_stack_detail(tenant_id: str, stack_name: str, stack_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    stack = store.get_stack(stack_id)
    if stack is None:
        return JSONResponse(status_code=404, content={"error": {"code": 404, "message": "Stack not found"}})
    return {"stack": _stack_detail(stack)}


@router.get("/v1/{tenant_id}/stacks/{stack_name}")
async def get_stack_by_name(tenant_id: str, stack_name: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    stack = store.get_stack(stack_name)
    if stack is None:
        return JSONResponse(status_code=404, content={"error": {"code": 404, "message": "Stack not found"}})
    return {"stack": _stack_detail(stack)}


@router.put("/v1/{tenant_id}/stacks/{stack_name}/{stack_id}", status_code=202)
async def update_stack(tenant_id: str, stack_name: str, stack_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    template = body.get("template")
    parameters = body.get("parameters")
    stack = store.update_stack(stack_id, template=template, parameters=parameters)
    if stack is None:
        return JSONResponse(status_code=404, content={"error": {"code": 404, "message": "Stack not found"}})
    return Response(status_code=202)


@router.delete("/v1/{tenant_id}/stacks/{stack_name}/{stack_id}", status_code=204)
async def delete_stack(tenant_id: str, stack_name: str, stack_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    found = store.delete_stack(stack_id)
    if not found:
        return JSONResponse(status_code=404, content={"error": {"code": 404, "message": "Stack not found"}})
    return Response(status_code=204)


# ── Resources ─────────────────────────────────────────────────

@router.get("/v1/{tenant_id}/stacks/{stack_name}/{stack_id}/resources")
async def list_resources(tenant_id: str, stack_name: str, stack_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    resources = store.list_resources(stack_id)
    return {
        "resources": [_resource_dict(r, tenant_id, stack_name, stack_id) for r in resources]
    }


# ── Events ────────────────────────────────────────────────────

@router.get("/v1/{tenant_id}/stacks/{stack_name}/{stack_id}/events")
async def list_events(tenant_id: str, stack_name: str, stack_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    events = store.list_events(stack_id)
    return {"events": events}
