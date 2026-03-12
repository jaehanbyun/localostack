from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .models import (
    NetworkCreateRequest,
    PortCreateRequest,
    SecurityGroupCreateRequest,
    SecurityGroupRuleCreateRequest,
    SubnetCreateRequest,
)
from .store import NeutronStore

router = APIRouter()


def _error(code: int, message: str, error_type: str = "HTTPError") -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"NeutronError": {"type": error_type, "message": message, "detail": ""}},
    )


def _get_store(request: Request) -> NeutronStore:
    return request.app.state.neutron_store


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        raise _AuthError(_error(401, "Authentication required"))
    return token_id


class _AuthError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


# ── Serializers ────────────────────────────────────────────

def _network_to_dict(net) -> dict:
    return {
        "id": net.id,
        "name": net.name,
        "tenant_id": net.tenant_id,
        "admin_state_up": net.admin_state_up,
        "status": net.status,
        "shared": net.shared,
        "router:external": net.external,
        "mtu": net.mtu,
        "provider:network_type": net.provider_network_type,
        "subnets": net.subnets,
        "created_at": net.created_at,
        "updated_at": net.updated_at,
    }


def _subnet_to_dict(sub) -> dict:
    return {
        "id": sub.id,
        "name": sub.name,
        "network_id": sub.network_id,
        "tenant_id": sub.tenant_id,
        "cidr": sub.cidr,
        "ip_version": sub.ip_version,
        "gateway_ip": sub.gateway_ip,
        "allocation_pools": sub.allocation_pools,
        "dns_nameservers": sub.dns_nameservers,
        "enable_dhcp": sub.enable_dhcp,
        "created_at": sub.created_at,
        "updated_at": sub.updated_at,
    }


def _port_to_dict(port) -> dict:
    return {
        "id": port.id,
        "name": port.name,
        "network_id": port.network_id,
        "tenant_id": port.tenant_id,
        "mac_address": port.mac_address,
        "fixed_ips": port.fixed_ips,
        "status": port.status,
        "device_id": port.device_id,
        "device_owner": port.device_owner,
        "security_groups": port.security_groups,
        "admin_state_up": port.admin_state_up,
        "created_at": port.created_at,
        "updated_at": port.updated_at,
    }


def _security_group_to_dict(sg) -> dict:
    return {
        "id": sg.id,
        "name": sg.name,
        "tenant_id": sg.tenant_id,
        "description": sg.description,
        "security_group_rules": sg.security_group_rules,
        "created_at": sg.created_at,
        "updated_at": sg.updated_at,
    }


def _security_group_rule_to_dict(rule) -> dict:
    return {
        "id": rule.id,
        "security_group_id": rule.security_group_id,
        "tenant_id": rule.tenant_id,
        "direction": rule.direction,
        "ethertype": rule.ethertype,
        "protocol": rule.protocol,
        "port_range_min": rule.port_range_min,
        "port_range_max": rule.port_range_max,
        "remote_ip_prefix": rule.remote_ip_prefix,
        "remote_group_id": rule.remote_group_id,
    }


# ── Network CRUD ───────────────────────────────────────────

@router.get("/v2.0/networks")
async def list_networks(request: Request):
    _require_token(request)
    store = _get_store(request)
    params = request.query_params
    networks = store.list_networks()
    if params.get("name"):
        networks = [n for n in networks if n.name == params["name"]]
    if params.get("id"):
        networks = [n for n in networks if n.id == params["id"]]
    if params.get("status"):
        networks = [n for n in networks if n.status == params["status"]]
    return {"networks": [_network_to_dict(n) for n in networks]}


@router.post("/v2.0/networks", status_code=201)
async def create_network(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("network", body)
    req = NetworkCreateRequest(**data)
    net = store.create_network(
        name=req.name,
        tenant_id=req.tenant_id,
        admin_state_up=req.admin_state_up,
        shared=req.shared,
        external=req.external,
        mtu=req.mtu,
        provider_network_type=req.provider_network_type,
    )
    return JSONResponse(status_code=201, content={"network": _network_to_dict(net)})


@router.get("/v2.0/networks/{network_id}")
async def get_network(network_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    net = store.get_network(network_id)
    if net is None:
        return _error(404, "Network not found", "NetworkNotFound")
    return {"network": _network_to_dict(net)}


@router.put("/v2.0/networks/{network_id}")
async def update_network(network_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    net = store.get_network(network_id)
    if net is None:
        return _error(404, "Network not found", "NetworkNotFound")
    body = await request.json()
    data = body.get("network", body)
    updates = {}
    for key in ("name", "admin_state_up", "shared", "external", "mtu"):
        if key in data:
            updates[key] = data[key]
    net = store.update_network(network_id, **updates)
    return {"network": _network_to_dict(net)}


@router.delete("/v2.0/networks/{network_id}")
async def delete_network(network_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_network(network_id):
        return _error(404, "Network not found", "NetworkNotFound")
    return Response(status_code=204)


# ── Subnet CRUD ────────────────────────────────────────────

@router.get("/v2.0/subnets")
async def list_subnets(request: Request):
    _require_token(request)
    store = _get_store(request)
    subnets = store.list_subnets()
    return {"subnets": [_subnet_to_dict(s) for s in subnets]}


@router.post("/v2.0/subnets", status_code=201)
async def create_subnet(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("subnet", body)
    req = SubnetCreateRequest(**data)
    subnet = store.create_subnet(
        name=req.name,
        network_id=req.network_id,
        cidr=req.cidr,
        tenant_id=req.tenant_id,
        ip_version=req.ip_version,
        gateway_ip=req.gateway_ip,
        allocation_pools=req.allocation_pools,
        dns_nameservers=req.dns_nameservers,
        enable_dhcp=req.enable_dhcp,
    )
    if subnet is None:
        return _error(404, "Network not found", "NetworkNotFound")
    return JSONResponse(status_code=201, content={"subnet": _subnet_to_dict(subnet)})


@router.get("/v2.0/subnets/{subnet_id}")
async def get_subnet(subnet_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    subnet = store.get_subnet(subnet_id)
    if subnet is None:
        return _error(404, "Subnet not found", "SubnetNotFound")
    return {"subnet": _subnet_to_dict(subnet)}


@router.put("/v2.0/subnets/{subnet_id}")
async def update_subnet(subnet_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    subnet = store.get_subnet(subnet_id)
    if subnet is None:
        return _error(404, "Subnet not found", "SubnetNotFound")
    body = await request.json()
    data = body.get("subnet", body)
    updates = {}
    for key in ("name", "gateway_ip", "dns_nameservers", "enable_dhcp"):
        if key in data:
            updates[key] = data[key]
    subnet = store.update_subnet(subnet_id, **updates)
    return {"subnet": _subnet_to_dict(subnet)}


@router.delete("/v2.0/subnets/{subnet_id}")
async def delete_subnet(subnet_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_subnet(subnet_id):
        return _error(404, "Subnet not found", "SubnetNotFound")
    return Response(status_code=204)


# ── Port CRUD ──────────────────────────────────────────────

@router.get("/v2.0/ports")
async def list_ports(request: Request):
    _require_token(request)
    store = _get_store(request)
    network_id = request.query_params.get("network_id")
    device_id = request.query_params.get("device_id")
    ports = store.list_ports(network_id=network_id, device_id=device_id)
    return {"ports": [_port_to_dict(p) for p in ports]}


@router.post("/v2.0/ports", status_code=201)
async def create_port(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("port", body)
    req = PortCreateRequest(**data)
    port = store.create_port(
        name=req.name,
        network_id=req.network_id,
        tenant_id=req.tenant_id,
        fixed_ips=req.fixed_ips,
        device_id=req.device_id,
        device_owner=req.device_owner,
        security_groups=req.security_groups,
        admin_state_up=req.admin_state_up,
    )
    if port is None:
        return _error(404, "Network not found", "NetworkNotFound")
    return JSONResponse(status_code=201, content={"port": _port_to_dict(port)})


@router.get("/v2.0/ports/{port_id}")
async def get_port(port_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    port = store.get_port(port_id)
    if port is None:
        return _error(404, "Port not found", "PortNotFound")
    return {"port": _port_to_dict(port)}


@router.put("/v2.0/ports/{port_id}")
async def update_port(port_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    port = store.get_port(port_id)
    if port is None:
        return _error(404, "Port not found", "PortNotFound")
    body = await request.json()
    data = body.get("port", body)
    updates = {}
    for key in ("name", "device_id", "device_owner", "security_groups", "admin_state_up"):
        if key in data:
            updates[key] = data[key]
    port = store.update_port(port_id, **updates)
    return {"port": _port_to_dict(port)}


@router.delete("/v2.0/ports/{port_id}")
async def delete_port(port_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_port(port_id):
        return _error(404, "Port not found", "PortNotFound")
    return Response(status_code=204)


# ── Security Group CRUD ────────────────────────────────────

@router.get("/v2.0/security-groups")
async def list_security_groups(request: Request):
    _require_token(request)
    store = _get_store(request)
    groups = store.list_security_groups()
    return {"security_groups": [_security_group_to_dict(sg) for sg in groups]}


@router.post("/v2.0/security-groups", status_code=201)
async def create_security_group(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("security_group", body)
    req = SecurityGroupCreateRequest(**data)
    sg = store.create_security_group(
        name=req.name,
        tenant_id=req.tenant_id,
        description=req.description,
    )
    return JSONResponse(status_code=201, content={"security_group": _security_group_to_dict(sg)})


@router.get("/v2.0/security-groups/{sg_id}")
async def get_security_group(sg_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    sg = store.get_security_group(sg_id)
    if sg is None:
        return _error(404, "Security group not found", "SecurityGroupNotFound")
    return {"security_group": _security_group_to_dict(sg)}


@router.put("/v2.0/security-groups/{sg_id}")
async def update_security_group(sg_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    sg = store.get_security_group(sg_id)
    if sg is None:
        return _error(404, "Security group not found", "SecurityGroupNotFound")
    body = await request.json()
    data = body.get("security_group", body)
    updates = {}
    for key in ("name", "description"):
        if key in data:
            updates[key] = data[key]
    sg = store.update_security_group(sg_id, **updates)
    return {"security_group": _security_group_to_dict(sg)}


@router.delete("/v2.0/security-groups/{sg_id}")
async def delete_security_group(sg_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_security_group(sg_id):
        return _error(404, "Security group not found", "SecurityGroupNotFound")
    return Response(status_code=204)


# ── Security Group Rule CRUD ──────────────────────────────

@router.get("/v2.0/security-group-rules")
async def list_security_group_rules(request: Request):
    _require_token(request)
    store = _get_store(request)
    rules = store.list_security_group_rules()
    return {"security_group_rules": [_security_group_rule_to_dict(r) for r in rules]}


@router.post("/v2.0/security-group-rules", status_code=201)
async def create_security_group_rule(request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("security_group_rule", body)
    req = SecurityGroupRuleCreateRequest(**data)
    rule = store.create_security_group_rule(
        security_group_id=req.security_group_id,
        direction=req.direction,
        tenant_id=req.tenant_id,
        ethertype=req.ethertype,
        protocol=req.protocol,
        port_range_min=req.port_range_min,
        port_range_max=req.port_range_max,
        remote_ip_prefix=req.remote_ip_prefix,
        remote_group_id=req.remote_group_id,
    )
    if rule is None:
        return _error(404, "Security group not found", "SecurityGroupNotFound")
    return JSONResponse(status_code=201, content={"security_group_rule": _security_group_rule_to_dict(rule)})


@router.get("/v2.0/security-group-rules/{rule_id}")
async def get_security_group_rule(rule_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    rule = store.get_security_group_rule(rule_id)
    if rule is None:
        return _error(404, "Security group rule not found", "SecurityGroupRuleNotFound")
    return {"security_group_rule": _security_group_rule_to_dict(rule)}


@router.delete("/v2.0/security-group-rules/{rule_id}")
async def delete_security_group_rule(rule_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_security_group_rule(rule_id):
        return _error(404, "Security group rule not found", "SecurityGroupRuleNotFound")
    return Response(status_code=204)


# ── Extensions ─────────────────────────────────────────────

@router.get("/v2.0/extensions")
async def list_extensions(request: Request):
    _require_token(request)
    return {"extensions": []}
