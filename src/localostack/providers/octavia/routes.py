"""Octavia Load Balancer API routes."""
from __future__ import annotations

from fastapi import APIRouter, Request, Response

from .store import OctaviaStore

router = APIRouter()


def _get_store(request: Request) -> OctaviaStore:
    return request.app.state.octavia_store


def _require_token(request: Request) -> str | None:
    return request.headers.get("X-Auth-Token")


def _lb_dict(lb) -> dict:
    return {
        "id": lb.id, "name": lb.name,
        "vip_address": lb.vip_address,
        "vip_network_id": lb.vip_network_id,
        "vip_subnet_id": lb.vip_subnet_id,
        "provisioning_status": lb.provisioning_status,
        "operating_status": lb.operating_status,
        "admin_state_up": lb.admin_state_up,
        "project_id": lb.project_id,
        "description": lb.description,
        "created_at": lb.created_at,
        "updated_at": lb.updated_at,
        "listeners": [],
    }


def _listener_dict(ln) -> dict:
    return {
        "id": ln.id, "name": ln.name,
        "loadbalancers": [{"id": ln.loadbalancer_id}],
        "protocol": ln.protocol,
        "protocol_port": ln.protocol_port,
        "connection_limit": ln.connection_limit,
        "provisioning_status": ln.provisioning_status,
        "operating_status": ln.operating_status,
        "admin_state_up": ln.admin_state_up,
        "description": ln.description,
        "default_pool_id": ln.default_pool_id,
        "created_at": ln.created_at,
        "updated_at": ln.updated_at,
    }


def _pool_dict(p) -> dict:
    return {
        "id": p.id, "name": p.name,
        "listeners": [{"id": p.listener_id}] if p.listener_id else [],
        "loadbalancers": [{"id": p.loadbalancer_id}] if p.loadbalancer_id else [],
        "protocol": p.protocol,
        "lb_algorithm": p.lb_algorithm,
        "session_persistence": p.session_persistence,
        "provisioning_status": p.provisioning_status,
        "operating_status": p.operating_status,
        "admin_state_up": p.admin_state_up,
        "description": p.description,
        "created_at": p.created_at,
        "updated_at": p.updated_at,
    }


def _member_dict(m) -> dict:
    return {
        "id": m.id, "name": m.name,
        "pool_id": m.pool_id,
        "address": m.address,
        "protocol_port": m.protocol_port,
        "weight": m.weight,
        "subnet_id": m.subnet_id,
        "provisioning_status": m.provisioning_status,
        "operating_status": m.operating_status,
        "admin_state_up": m.admin_state_up,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


# ── LoadBalancers ─────────────────────────────────────────────────────

@router.get("/v2/lbaas/loadbalancers")
async def list_loadbalancers(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    return {"loadbalancers": [_lb_dict(lb) for lb in store.list_loadbalancers()]}


@router.post("/v2/lbaas/loadbalancers", status_code=201)
async def create_loadbalancer(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    data = body.get("loadbalancer", body)
    lb = store.create_loadbalancer(
        name=data.get("name", ""),
        vip_address=data.get("vip_address", "10.0.0.100"),
        vip_network_id=data.get("vip_network_id", ""),
        vip_subnet_id=data.get("vip_subnet_id", ""),
        project_id=data.get("project_id", ""),
        description=data.get("description", ""),
    )
    return {"loadbalancer": _lb_dict(lb)}


@router.get("/v2/lbaas/loadbalancers/{lb_id}")
async def get_loadbalancer(lb_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    lb = store.get_loadbalancer(lb_id)
    if lb is None:
        return Response(status_code=404)
    return {"loadbalancer": _lb_dict(lb)}


@router.put("/v2/lbaas/loadbalancers/{lb_id}")
async def update_loadbalancer(lb_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    data = body.get("loadbalancer", body)
    lb = store.update_loadbalancer(lb_id, **{k: v for k, v in data.items() if k != "id"})
    if lb is None:
        return Response(status_code=404)
    return {"loadbalancer": _lb_dict(lb)}


@router.delete("/v2/lbaas/loadbalancers/{lb_id}")
async def delete_loadbalancer(lb_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_loadbalancer(lb_id):
        return Response(status_code=404)
    return Response(status_code=204)


# ── Listeners ─────────────────────────────────────────────────────────

@router.get("/v2/lbaas/listeners")
async def list_listeners(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    return {"listeners": [_listener_dict(ln) for ln in store.list_listeners()]}


@router.post("/v2/lbaas/listeners", status_code=201)
async def create_listener(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    data = body.get("listener", body)
    ln = store.create_listener(
        name=data.get("name", ""),
        loadbalancer_id=data.get("loadbalancer_id", ""),
        protocol=data.get("protocol", "HTTP"),
        protocol_port=data.get("protocol_port", 80),
        connection_limit=data.get("connection_limit", -1),
        description=data.get("description", ""),
    )
    return {"listener": _listener_dict(ln)}


@router.get("/v2/lbaas/listeners/{listener_id}")
async def get_listener(listener_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    ln = store.get_listener(listener_id)
    if ln is None:
        return Response(status_code=404)
    return {"listener": _listener_dict(ln)}


@router.delete("/v2/lbaas/listeners/{listener_id}")
async def delete_listener(listener_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_listener(listener_id):
        return Response(status_code=404)
    return Response(status_code=204)


# ── Pools ─────────────────────────────────────────────────────────────

@router.get("/v2/lbaas/pools")
async def list_pools(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    return {"pools": [_pool_dict(p) for p in store.list_pools()]}


@router.post("/v2/lbaas/pools", status_code=201)
async def create_pool(request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    data = body.get("pool", body)
    pool = store.create_pool(
        name=data.get("name", ""),
        listener_id=data.get("listener_id", ""),
        loadbalancer_id=data.get("loadbalancer_id", ""),
        protocol=data.get("protocol", "HTTP"),
        lb_algorithm=data.get("lb_algorithm", "ROUND_ROBIN"),
        description=data.get("description", ""),
    )
    return {"pool": _pool_dict(pool)}


@router.get("/v2/lbaas/pools/{pool_id}")
async def get_pool(pool_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    pool = store.get_pool(pool_id)
    if pool is None:
        return Response(status_code=404)
    return {"pool": _pool_dict(pool)}


@router.delete("/v2/lbaas/pools/{pool_id}")
async def delete_pool(pool_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_pool(pool_id):
        return Response(status_code=404)
    return Response(status_code=204)


# ── Members ───────────────────────────────────────────────────────────

@router.get("/v2/lbaas/pools/{pool_id}/members")
async def list_members(pool_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    return {"members": [_member_dict(m) for m in store.list_members(pool_id)]}


@router.post("/v2/lbaas/pools/{pool_id}/members", status_code=201)
async def create_member(pool_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    body = await request.json()
    data = body.get("member", body)
    m = store.create_member(
        pool_id=pool_id,
        name=data.get("name", ""),
        address=data.get("address", ""),
        protocol_port=data.get("protocol_port", 80),
        weight=data.get("weight", 1),
        subnet_id=data.get("subnet_id", ""),
    )
    return {"member": _member_dict(m)}


@router.delete("/v2/lbaas/pools/{pool_id}/members/{member_id}")
async def delete_member(pool_id: str, member_id: str, request: Request):
    if not _require_token(request):
        return Response(status_code=401)
    store = _get_store(request)
    if not store.delete_member(member_id, pool_id):
        return Response(status_code=404)
    return Response(status_code=204)
