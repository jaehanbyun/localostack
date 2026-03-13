"""Octavia Load Balancer store."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class LoadBalancer:
    id: str
    name: str
    vip_address: str = "10.0.0.100"
    vip_network_id: str = ""
    vip_subnet_id: str = ""
    provisioning_status: str = "ACTIVE"
    operating_status: str = "ONLINE"
    admin_state_up: bool = True
    project_id: str = ""
    description: str = ""
    flavor_id: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class Listener:
    id: str
    name: str
    loadbalancer_id: str
    protocol: str = "HTTP"
    protocol_port: int = 80
    connection_limit: int = -1
    provisioning_status: str = "ACTIVE"
    operating_status: str = "ONLINE"
    admin_state_up: bool = True
    description: str = ""
    default_pool_id: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class Pool:
    id: str
    name: str
    listener_id: str
    loadbalancer_id: str = ""
    protocol: str = "HTTP"
    lb_algorithm: str = "ROUND_ROBIN"
    session_persistence: Optional[dict] = None
    provisioning_status: str = "ACTIVE"
    operating_status: str = "ONLINE"
    admin_state_up: bool = True
    description: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class Member:
    id: str
    name: str
    pool_id: str
    address: str
    protocol_port: int
    weight: int = 1
    subnet_id: str = ""
    provisioning_status: str = "ACTIVE"
    operating_status: str = "ONLINE"
    admin_state_up: bool = True
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


class OctaviaStore:
    def __init__(self, backend=None):
        self._b = backend
        self.loadbalancers: dict[str, LoadBalancer] = {}
        self.listeners: dict[str, Listener] = {}
        self.pools: dict[str, Pool] = {}
        self.members: dict[str, Member] = {}

    def _save(self, rtype: str, id: str, data: dict) -> None:
        if self._b:
            self._b.put("octavia", rtype, id, data)

    def _del(self, rtype: str, id: str) -> None:
        if self._b:
            self._b.delete("octavia", rtype, id)

    def bootstrap(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("octavia", "loadbalancers"):
            lb = LoadBalancer(**data)
            self.loadbalancers[lb.id] = lb
        for data in self._b.get_all("octavia", "listeners"):
            ln = Listener(**data)
            self.listeners[ln.id] = ln
        for data in self._b.get_all("octavia", "pools"):
            p = Pool(**data)
            self.pools[p.id] = p
        for data in self._b.get_all("octavia", "members"):
            m = Member(**data)
            self.members[m.id] = m

    # ── LoadBalancer ──

    def create_loadbalancer(self, *, name: str, vip_address: str = "10.0.0.100",
                             vip_network_id: str = "", vip_subnet_id: str = "",
                             project_id: str = "", description: str = "") -> LoadBalancer:
        lb = LoadBalancer(id=str(uuid.uuid4()), name=name, vip_address=vip_address,
                          vip_network_id=vip_network_id, vip_subnet_id=vip_subnet_id,
                          project_id=project_id, description=description)
        self.loadbalancers[lb.id] = lb
        self._save("loadbalancers", lb.id, asdict(lb))
        return lb

    def get_loadbalancer(self, lb_id: str) -> Optional[LoadBalancer]:
        return self.loadbalancers.get(lb_id)

    def list_loadbalancers(self) -> list[LoadBalancer]:
        return list(self.loadbalancers.values())

    def update_loadbalancer(self, lb_id: str, **kwargs) -> Optional[LoadBalancer]:
        lb = self.loadbalancers.get(lb_id)
        if lb is None:
            return None
        for k, v in kwargs.items():
            if hasattr(lb, k):
                setattr(lb, k, v)
        lb.updated_at = _now()
        self._save("loadbalancers", lb.id, asdict(lb))
        return lb

    def delete_loadbalancer(self, lb_id: str) -> bool:
        if lb_id not in self.loadbalancers:
            return False
        del self.loadbalancers[lb_id]
        self._del("loadbalancers", lb_id)
        return True

    # ── Listener ──

    def create_listener(self, *, name: str, loadbalancer_id: str,
                         protocol: str = "HTTP", protocol_port: int = 80,
                         connection_limit: int = -1, description: str = "") -> Listener:
        ln = Listener(id=str(uuid.uuid4()), name=name, loadbalancer_id=loadbalancer_id,
                      protocol=protocol, protocol_port=protocol_port,
                      connection_limit=connection_limit, description=description)
        self.listeners[ln.id] = ln
        self._save("listeners", ln.id, asdict(ln))
        return ln

    def get_listener(self, listener_id: str) -> Optional[Listener]:
        return self.listeners.get(listener_id)

    def list_listeners(self) -> list[Listener]:
        return list(self.listeners.values())

    def delete_listener(self, listener_id: str) -> bool:
        if listener_id not in self.listeners:
            return False
        del self.listeners[listener_id]
        self._del("listeners", listener_id)
        return True

    # ── Pool ──

    def create_pool(self, *, name: str, listener_id: str, loadbalancer_id: str = "",
                     protocol: str = "HTTP", lb_algorithm: str = "ROUND_ROBIN",
                     description: str = "") -> Pool:
        pool = Pool(id=str(uuid.uuid4()), name=name, listener_id=listener_id,
                    loadbalancer_id=loadbalancer_id, protocol=protocol,
                    lb_algorithm=lb_algorithm, description=description)
        self.pools[pool.id] = pool
        self._save("pools", pool.id, asdict(pool))
        return pool

    def get_pool(self, pool_id: str) -> Optional[Pool]:
        return self.pools.get(pool_id)

    def list_pools(self) -> list[Pool]:
        return list(self.pools.values())

    def delete_pool(self, pool_id: str) -> bool:
        if pool_id not in self.pools:
            return False
        del self.pools[pool_id]
        self._del("pools", pool_id)
        return True

    # ── Member ──

    def create_member(self, *, pool_id: str, name: str, address: str,
                       protocol_port: int, weight: int = 1,
                       subnet_id: str = "") -> Member:
        m = Member(id=str(uuid.uuid4()), name=name, pool_id=pool_id,
                   address=address, protocol_port=protocol_port,
                   weight=weight, subnet_id=subnet_id)
        self.members[m.id] = m
        self._save("members", m.id, asdict(m))
        return m

    def get_member(self, member_id: str, pool_id: str) -> Optional[Member]:
        m = self.members.get(member_id)
        if m and m.pool_id == pool_id:
            return m
        return None

    def list_members(self, pool_id: str) -> list[Member]:
        return [m for m in self.members.values() if m.pool_id == pool_id]

    def delete_member(self, member_id: str, pool_id: str) -> bool:
        m = self.members.get(member_id)
        if m is None or m.pool_id != pool_id:
            return False
        del self.members[member_id]
        self._del("members", member_id)
        return True
