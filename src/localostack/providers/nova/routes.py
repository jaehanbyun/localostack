"""Nova API routes."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .models import FlavorCreateRequest, KeypairCreateRequest, ServerCreateRequest
from .store import NovaStore

router = APIRouter()


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": {"message": message, "code": code}},
    )


def _get_store(request: Request) -> NovaStore:
    return request.app.state.nova_store


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        raise _AuthError(_error(401, "Authentication required"))
    return token_id


class _AuthError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


# ── Serializers ───────────────────────────────────────────

def _server_brief(srv) -> dict:
    return {
        "id": srv.id,
        "name": srv.name,
        "links": [
            {"rel": "self", "href": f"/v2.1/servers/{srv.id}"},
            {"rel": "bookmark", "href": f"/servers/{srv.id}"},
        ],
    }


def _server_detail(srv) -> dict:
    return {
        "id": srv.id,
        "name": srv.name,
        "status": srv.status,
        "tenant_id": srv.tenant_id,
        "user_id": srv.user_id,
        "image": {"id": srv.image_ref} if srv.image_ref else "",
        "flavor": {"id": srv.flavor_id},
        "addresses": srv.addresses,
        "key_name": srv.key_name,
        "security_groups": srv.security_groups,
        "metadata": srv.metadata,
        "created": srv.created_at,
        "updated": srv.updated_at,
        "OS-EXT-STS:vm_state": srv.vm_state,
        "OS-EXT-STS:task_state": srv.task_state,
        "OS-EXT-STS:power_state": srv.power_state,
        "OS-EXT-SRV-ATTR:host": srv.host,
        "OS-EXT-AZ:availability_zone": srv.availability_zone,
        "os-extended-volumes:volumes_attached": srv.volumes_attached,
        "hostId": srv.host,
        "config_drive": "",
        "progress": 100 if srv.status == "ACTIVE" else 0,
        "links": [
            {"rel": "self", "href": f"/v2.1/servers/{srv.id}"},
            {"rel": "bookmark", "href": f"/servers/{srv.id}"},
        ],
    }


def _server_create_response(srv) -> dict:
    return {
        "id": srv.id,
        "name": srv.name,
        "status": srv.status,
        "links": [
            {"rel": "self", "href": f"/v2.1/servers/{srv.id}"},
            {"rel": "bookmark", "href": f"/servers/{srv.id}"},
        ],
        "adminPass": secrets.token_urlsafe(12),
        "security_groups": srv.security_groups,
    }


def _flavor_brief(f) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "links": [
            {"rel": "self", "href": f"/v2.1/flavors/{f.id}"},
            {"rel": "bookmark", "href": f"/flavors/{f.id}"},
        ],
    }


def _flavor_detail(f) -> dict:
    return {
        "id": f.id,
        "name": f.name,
        "vcpus": f.vcpus,
        "ram": f.ram,
        "disk": f.disk,
        "OS-FLV-EXT-DATA:ephemeral": f.ephemeral,
        "swap": f.swap,
        "rxtx_factor": f.rxtx_factor,
        "os-flavor-access:is_public": f.is_public,
        "links": [
            {"rel": "self", "href": f"/v2.1/flavors/{f.id}"},
            {"rel": "bookmark", "href": f"/flavors/{f.id}"},
        ],
    }


def _keypair_brief(kp) -> dict:
    return {
        "keypair": {
            "name": kp.name,
            "public_key": kp.public_key,
            "fingerprint": kp.fingerprint,
            "type": kp.type,
        }
    }


def _keypair_detail(kp) -> dict:
    return {
        "keypair": {
            "name": kp.name,
            "public_key": kp.public_key,
            "fingerprint": kp.fingerprint,
            "type": kp.type,
            "user_id": kp.user_id,
            "created_at": kp.created_at,
        }
    }


# ── Server CRUD ───────────────────────────────────────────

@router.get("/v2.1/servers")
async def list_servers(request: Request):
    _require_token(request)
    store = _get_store(request)
    servers = store.list_servers()
    return {"servers": [_server_brief(s) for s in servers]}


@router.get("/v2.1/servers/detail")
async def list_servers_detail(request: Request):
    _require_token(request)
    store = _get_store(request)
    servers = store.list_servers()
    return {"servers": [_server_detail(s) for s in servers]}


@router.post("/v2.1/servers", status_code=202)
async def create_server(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("server", body)
    req = ServerCreateRequest(**data)
    srv = store.create_server(
        name=req.name,
        image_ref=req.imageRef,
        flavor_ref=req.flavorRef,
        key_name=req.key_name,
        security_groups=req.security_groups,
        networks=req.networks,
        metadata=req.metadata,
    )
    return JSONResponse(
        status_code=202,
        content={"server": _server_create_response(srv)},
    )


@router.get("/v2.1/servers/{server_id}")
async def get_server(server_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    srv = store.get_server(server_id)
    if srv is None or srv.status == "DELETED":
        return _error(404, "Instance not found")
    return {"server": _server_detail(srv)}


@router.put("/v2.1/servers/{server_id}")
async def update_server(server_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    srv = store.get_server(server_id)
    if srv is None or srv.status == "DELETED":
        return _error(404, "Instance not found")
    body = await request.json()
    data = body.get("server", body)
    updates = {}
    if "name" in data:
        updates["name"] = data["name"]
    srv = store.update_server(server_id, **updates)
    return {"server": _server_detail(srv)}


@router.delete("/v2.1/servers/{server_id}")
async def delete_server(server_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_server(server_id):
        return _error(404, "Instance not found")
    return Response(status_code=204)


# ── Server Actions ────────────────────────────────────────

@router.post("/v2.1/servers/{server_id}/action")
async def server_action(server_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()

    action = None
    if "os-start" in body:
        action = "start"
    elif "os-stop" in body:
        action = "stop"
    elif "reboot" in body:
        action = "reboot"

    if action is None:
        return _error(400, "Invalid server action")

    srv = store.server_action(server_id, action)
    if srv is None:
        return _error(409, "Cannot perform action in current state")
    return Response(status_code=202)


# ── Flavor CRUD ───────────────────────────────────────────

@router.get("/v2.1/flavors")
async def list_flavors(request: Request):
    _require_token(request)
    store = _get_store(request)
    flavors = store.list_flavors()
    return {"flavors": [_flavor_brief(f) for f in flavors]}


@router.get("/v2.1/flavors/detail")
async def list_flavors_detail(request: Request):
    _require_token(request)
    store = _get_store(request)
    flavors = store.list_flavors()
    return {"flavors": [_flavor_detail(f) for f in flavors]}


@router.get("/v2.1/flavors/{flavor_id}")
async def get_flavor(flavor_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    flavor = store.get_flavor(flavor_id)
    if flavor is None:
        return _error(404, "Flavor not found")
    return {"flavor": _flavor_detail(flavor)}


@router.post("/v2.1/flavors", status_code=200)
async def create_flavor(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("flavor", body)
    req = FlavorCreateRequest(**data)
    flavor = store.create_flavor(
        name=req.name,
        vcpus=req.vcpus,
        ram=req.ram,
        disk=req.disk,
        ephemeral=req.ephemeral,
        swap=str(req.swap) if req.swap else "",
        rxtx_factor=req.rxtx_factor,
        is_public=req.is_public,
        id=req.id,
    )
    return {"flavor": _flavor_detail(flavor)}


# ── Keypair CRUD ──────────────────────────────────────────

@router.get("/v2.1/os-keypairs")
async def list_keypairs(request: Request):
    _require_token(request)
    store = _get_store(request)
    keypairs = store.list_keypairs()
    return {"keypairs": [_keypair_brief(kp) for kp in keypairs]}


@router.post("/v2.1/os-keypairs", status_code=200)
async def create_keypair(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("keypair", body)
    req = KeypairCreateRequest(**data)
    kp = store.create_keypair(
        name=req.name,
        user_id=req.user_id or "",
        public_key=req.public_key,
        type=req.type,
    )
    return {"keypair": _keypair_detail(kp)["keypair"]}


@router.get("/v2.1/os-keypairs/{name}")
async def get_keypair(name: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    kp = store.get_keypair(name)
    if kp is None:
        return _error(404, "Keypair not found")
    return _keypair_detail(kp)


@router.delete("/v2.1/os-keypairs/{name}")
async def delete_keypair(name: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_keypair(name):
        return _error(404, "Keypair not found")
    return Response(status_code=204)


# ── Limits ────────────────────────────────────────────────

@router.get("/v2.1/limits")
async def get_limits(request: Request):
    _require_token(request)
    store = _get_store(request)
    servers = store.list_servers()

    total_instances = len(servers)
    total_cores = 0
    total_ram = 0
    for srv in servers:
        flavor = store.get_flavor(srv.flavor_id)
        if flavor:
            total_cores += flavor.vcpus
            total_ram += flavor.ram

    return {
        "limits": {
            "absolute": {
                "maxTotalCores": 100,
                "maxTotalInstances": 50,
                "maxTotalRAMSize": 204800,
                "maxTotalKeypairs": 100,
                "totalCoresUsed": total_cores,
                "totalInstancesUsed": total_instances,
                "totalRAMUsed": total_ram,
            },
            "rate": [],
        }
    }
