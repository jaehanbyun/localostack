from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Network ────────────────────────────────────────────────

class NetworkCreateRequest(BaseModel):
    name: str
    tenant_id: str = ""
    admin_state_up: bool = True
    shared: bool = False
    external: bool = False
    mtu: int = 1500
    provider_network_type: str = "flat"


class NetworkUpdateRequest(BaseModel):
    name: Optional[str] = None
    admin_state_up: Optional[bool] = None
    shared: Optional[bool] = None
    external: Optional[bool] = None
    mtu: Optional[int] = None


# ── Subnet ─────────────────────────────────────────────────

class SubnetCreateRequest(BaseModel):
    name: str = ""
    network_id: str
    cidr: str
    tenant_id: str = ""
    ip_version: int = 4
    gateway_ip: Optional[str] = None
    allocation_pools: Optional[list[dict]] = None
    dns_nameservers: list[str] = []
    enable_dhcp: bool = True


class SubnetUpdateRequest(BaseModel):
    name: Optional[str] = None
    gateway_ip: Optional[str] = None
    dns_nameservers: Optional[list[str]] = None
    enable_dhcp: Optional[bool] = None


# ── Port ───────────────────────────────────────────────────

class PortCreateRequest(BaseModel):
    name: str = ""
    network_id: str
    tenant_id: str = ""
    fixed_ips: Optional[list[dict]] = None
    device_id: str = ""
    device_owner: str = ""
    security_groups: Optional[list[str]] = None
    admin_state_up: bool = True


class PortUpdateRequest(BaseModel):
    name: Optional[str] = None
    device_id: Optional[str] = None
    device_owner: Optional[str] = None
    security_groups: Optional[list[str]] = None
    admin_state_up: Optional[bool] = None


# ── Security Group ─────────────────────────────────────────

class SecurityGroupCreateRequest(BaseModel):
    name: str
    tenant_id: str = ""
    description: str = ""


class SecurityGroupUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


# ── Security Group Rule ────────────────────────────────────

class SecurityGroupRuleCreateRequest(BaseModel):
    security_group_id: str
    direction: str
    tenant_id: str = ""
    ethertype: str = "IPv4"
    protocol: Optional[str] = None
    port_range_min: Optional[int] = None
    port_range_max: Optional[int] = None
    remote_ip_prefix: Optional[str] = None
    remote_group_id: Optional[str] = None
