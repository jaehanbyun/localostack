from __future__ import annotations

import ipaddress
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Network:
    id: str
    name: str
    tenant_id: str = ""
    admin_state_up: bool = True
    status: str = "ACTIVE"
    shared: bool = False
    external: bool = False
    mtu: int = 1500
    provider_network_type: str = "flat"
    subnets: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Subnet:
    id: str
    name: str
    network_id: str
    tenant_id: str = ""
    cidr: str = ""
    ip_version: int = 4
    gateway_ip: str = ""
    allocation_pools: list[dict] = field(default_factory=list)
    dns_nameservers: list[str] = field(default_factory=list)
    enable_dhcp: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Port:
    id: str
    name: str
    network_id: str
    tenant_id: str = ""
    mac_address: str = ""
    fixed_ips: list[dict] = field(default_factory=list)
    status: str = "ACTIVE"
    device_id: str = ""
    device_owner: str = ""
    security_groups: list[str] = field(default_factory=list)
    admin_state_up: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SecurityGroup:
    id: str
    name: str
    tenant_id: str = ""
    description: str = ""
    security_group_rules: list[dict] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SecurityGroupRule:
    id: str
    security_group_id: str
    tenant_id: str = ""
    direction: str = "ingress"
    ethertype: str = "IPv4"
    protocol: Optional[str] = None
    port_range_min: Optional[int] = None
    port_range_max: Optional[int] = None
    remote_ip_prefix: Optional[str] = None
    remote_group_id: Optional[str] = None


class NeutronStore:
    def __init__(self):
        self.networks: dict[str, Network] = {}
        self.subnets: dict[str, Subnet] = {}
        self.ports: dict[str, Port] = {}
        self.security_groups: dict[str, SecurityGroup] = {}
        self.security_group_rules: dict[str, SecurityGroupRule] = {}

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def _generate_mac() -> str:
        return "fa:16:3e:{:02x}:{:02x}:{:02x}".format(
            random.randint(0, 255),
            random.randint(0, 255),
            random.randint(0, 255),
        )

    def _allocate_ip(self, subnet_id: str) -> Optional[str]:
        subnet = self.subnets.get(subnet_id)
        if subnet is None or not subnet.allocation_pools:
            return None
        pool = subnet.allocation_pools[0]
        start = ipaddress.ip_address(pool["start"])
        end = ipaddress.ip_address(pool["end"])
        used = set()
        for port in self.ports.values():
            for fip in port.fixed_ips:
                if fip.get("subnet_id") == subnet_id:
                    used.add(fip["ip_address"])
        current = start
        while current <= end:
            if str(current) not in used:
                return str(current)
            current += 1
        return None

    def _add_default_egress_rules(self, sg: SecurityGroup):
        for ethertype in ("IPv4", "IPv6"):
            rule_id = self._uuid()
            rule = SecurityGroupRule(
                id=rule_id,
                security_group_id=sg.id,
                tenant_id=sg.tenant_id,
                direction="egress",
                ethertype=ethertype,
            )
            self.security_group_rules[rule_id] = rule
            sg.security_group_rules.append(self._rule_to_dict(rule))

    @staticmethod
    def _rule_to_dict(rule: SecurityGroupRule) -> dict:
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

    # ── Network CRUD ───────────────────────────────────────

    def create_network(
        self,
        *,
        name: str,
        tenant_id: str = "",
        admin_state_up: bool = True,
        shared: bool = False,
        external: bool = False,
        mtu: int = 1500,
        provider_network_type: str = "flat",
    ) -> Network:
        now = self._now()
        net = Network(
            id=self._uuid(),
            name=name,
            tenant_id=tenant_id,
            admin_state_up=admin_state_up,
            shared=shared,
            external=external,
            mtu=mtu,
            provider_network_type=provider_network_type,
            created_at=now,
            updated_at=now,
        )
        self.networks[net.id] = net
        return net

    def get_network(self, network_id: str) -> Optional[Network]:
        return self.networks.get(network_id)

    def list_networks(self, tenant_id: Optional[str] = None) -> list[Network]:
        result = []
        for net in self.networks.values():
            if tenant_id and not net.shared and net.tenant_id != tenant_id:
                continue
            result.append(net)
        return result

    def update_network(self, network_id: str, **kwargs) -> Optional[Network]:
        net = self.get_network(network_id)
        if net is None:
            return None
        for key, value in kwargs.items():
            if hasattr(net, key) and key not in ("id", "created_at", "subnets"):
                setattr(net, key, value)
        net.updated_at = self._now()
        return net

    def delete_network(self, network_id: str) -> bool:
        if network_id not in self.networks:
            return False
        del self.networks[network_id]
        return True

    # ── Subnet CRUD ────────────────────────────────────────

    def create_subnet(
        self,
        *,
        name: str,
        network_id: str,
        cidr: str,
        tenant_id: str = "",
        ip_version: int = 4,
        gateway_ip: Optional[str] = None,
        allocation_pools: Optional[list[dict]] = None,
        dns_nameservers: Optional[list[str]] = None,
        enable_dhcp: bool = True,
    ) -> Optional[Subnet]:
        net = self.get_network(network_id)
        if net is None:
            return None
        network_obj = ipaddress.ip_network(cidr, strict=False)
        if gateway_ip is None:
            gateway_ip = str(network_obj[1])
        if allocation_pools is None:
            allocation_pools = [
                {"start": str(network_obj[2]), "end": str(network_obj[-2])}
            ]
        now = self._now()
        subnet = Subnet(
            id=self._uuid(),
            name=name,
            network_id=network_id,
            tenant_id=tenant_id,
            cidr=cidr,
            ip_version=ip_version,
            gateway_ip=gateway_ip,
            allocation_pools=allocation_pools,
            dns_nameservers=dns_nameservers or [],
            enable_dhcp=enable_dhcp,
            created_at=now,
            updated_at=now,
        )
        self.subnets[subnet.id] = subnet
        net.subnets.append(subnet.id)
        return subnet

    def get_subnet(self, subnet_id: str) -> Optional[Subnet]:
        return self.subnets.get(subnet_id)

    def list_subnets(self, tenant_id: Optional[str] = None) -> list[Subnet]:
        result = []
        for sub in self.subnets.values():
            if tenant_id and sub.tenant_id != tenant_id:
                continue
            result.append(sub)
        return result

    def update_subnet(self, subnet_id: str, **kwargs) -> Optional[Subnet]:
        sub = self.get_subnet(subnet_id)
        if sub is None:
            return None
        for key, value in kwargs.items():
            if hasattr(sub, key) and key not in ("id", "created_at", "network_id"):
                setattr(sub, key, value)
        sub.updated_at = self._now()
        return sub

    def delete_subnet(self, subnet_id: str) -> bool:
        sub = self.subnets.get(subnet_id)
        if sub is None:
            return False
        net = self.networks.get(sub.network_id)
        if net and subnet_id in net.subnets:
            net.subnets.remove(subnet_id)
        del self.subnets[subnet_id]
        return True

    # ── Port CRUD ──────────────────────────────────────────

    def create_port(
        self,
        *,
        name: str = "",
        network_id: str,
        tenant_id: str = "",
        fixed_ips: Optional[list[dict]] = None,
        device_id: str = "",
        device_owner: str = "",
        security_groups: Optional[list[str]] = None,
        admin_state_up: bool = True,
    ) -> Optional[Port]:
        net = self.get_network(network_id)
        if net is None:
            return None
        mac = self._generate_mac()
        if fixed_ips is None:
            fixed_ips = []
            if net.subnets:
                subnet_id = net.subnets[0]
                ip = self._allocate_ip(subnet_id)
                if ip:
                    fixed_ips.append({"subnet_id": subnet_id, "ip_address": ip})
        else:
            for fip in fixed_ips:
                if "ip_address" not in fip and "subnet_id" in fip:
                    ip = self._allocate_ip(fip["subnet_id"])
                    if ip:
                        fip["ip_address"] = ip
        if security_groups is None:
            default_sg = self._find_default_security_group(tenant_id)
            security_groups = [default_sg.id] if default_sg else []
        now = self._now()
        port = Port(
            id=self._uuid(),
            name=name,
            network_id=network_id,
            tenant_id=tenant_id,
            mac_address=mac,
            fixed_ips=fixed_ips,
            device_id=device_id,
            device_owner=device_owner,
            security_groups=security_groups,
            admin_state_up=admin_state_up,
            created_at=now,
            updated_at=now,
        )
        self.ports[port.id] = port
        return port

    def _find_default_security_group(self, tenant_id: str) -> Optional[SecurityGroup]:
        for sg in self.security_groups.values():
            if sg.name == "default" and sg.tenant_id == tenant_id:
                return sg
        for sg in self.security_groups.values():
            if sg.name == "default":
                return sg
        return None

    def get_port(self, port_id: str) -> Optional[Port]:
        return self.ports.get(port_id)

    def list_ports(
        self,
        tenant_id: Optional[str] = None,
        network_id: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> list[Port]:
        result = []
        for port in self.ports.values():
            if tenant_id and port.tenant_id != tenant_id:
                continue
            if network_id and port.network_id != network_id:
                continue
            if device_id and port.device_id != device_id:
                continue
            result.append(port)
        return result

    def update_port(self, port_id: str, **kwargs) -> Optional[Port]:
        port = self.get_port(port_id)
        if port is None:
            return None
        for key, value in kwargs.items():
            if hasattr(port, key) and key not in ("id", "created_at", "mac_address"):
                setattr(port, key, value)
        port.updated_at = self._now()
        return port

    def delete_port(self, port_id: str) -> bool:
        if port_id not in self.ports:
            return False
        del self.ports[port_id]
        return True

    # ── Security Group CRUD ────────────────────────────────

    def create_security_group(
        self,
        *,
        name: str,
        tenant_id: str = "",
        description: str = "",
    ) -> SecurityGroup:
        now = self._now()
        sg = SecurityGroup(
            id=self._uuid(),
            name=name,
            tenant_id=tenant_id,
            description=description,
            created_at=now,
            updated_at=now,
        )
        self.security_groups[sg.id] = sg
        self._add_default_egress_rules(sg)
        return sg

    def get_security_group(self, sg_id: str) -> Optional[SecurityGroup]:
        return self.security_groups.get(sg_id)

    def list_security_groups(self, tenant_id: Optional[str] = None) -> list[SecurityGroup]:
        result = []
        for sg in self.security_groups.values():
            if tenant_id and sg.tenant_id != tenant_id:
                continue
            result.append(sg)
        return result

    def update_security_group(self, sg_id: str, **kwargs) -> Optional[SecurityGroup]:
        sg = self.get_security_group(sg_id)
        if sg is None:
            return None
        for key, value in kwargs.items():
            if hasattr(sg, key) and key not in ("id", "created_at", "security_group_rules"):
                setattr(sg, key, value)
        sg.updated_at = self._now()
        return sg

    def delete_security_group(self, sg_id: str) -> bool:
        if sg_id not in self.security_groups:
            return False
        rules_to_delete = [
            r_id for r_id, r in self.security_group_rules.items()
            if r.security_group_id == sg_id
        ]
        for r_id in rules_to_delete:
            del self.security_group_rules[r_id]
        del self.security_groups[sg_id]
        return True

    # ── Security Group Rule CRUD ───────────────────────────

    def create_security_group_rule(
        self,
        *,
        security_group_id: str,
        direction: str,
        tenant_id: str = "",
        ethertype: str = "IPv4",
        protocol: Optional[str] = None,
        port_range_min: Optional[int] = None,
        port_range_max: Optional[int] = None,
        remote_ip_prefix: Optional[str] = None,
        remote_group_id: Optional[str] = None,
    ) -> Optional[SecurityGroupRule]:
        sg = self.get_security_group(security_group_id)
        if sg is None:
            return None
        rule = SecurityGroupRule(
            id=self._uuid(),
            security_group_id=security_group_id,
            tenant_id=tenant_id,
            direction=direction,
            ethertype=ethertype,
            protocol=protocol,
            port_range_min=port_range_min,
            port_range_max=port_range_max,
            remote_ip_prefix=remote_ip_prefix,
            remote_group_id=remote_group_id,
        )
        self.security_group_rules[rule.id] = rule
        sg.security_group_rules.append(self._rule_to_dict(rule))
        return rule

    def get_security_group_rule(self, rule_id: str) -> Optional[SecurityGroupRule]:
        return self.security_group_rules.get(rule_id)

    def list_security_group_rules(self, tenant_id: Optional[str] = None) -> list[SecurityGroupRule]:
        result = []
        for rule in self.security_group_rules.values():
            if tenant_id and rule.tenant_id != tenant_id:
                continue
            result.append(rule)
        return result

    def delete_security_group_rule(self, rule_id: str) -> bool:
        rule = self.security_group_rules.get(rule_id)
        if rule is None:
            return False
        sg = self.security_groups.get(rule.security_group_id)
        if sg:
            sg.security_group_rules = [
                r for r in sg.security_group_rules if r["id"] != rule_id
            ]
        del self.security_group_rules[rule_id]
        return True

    # ── Bootstrap ──────────────────────────────────────────

    def bootstrap(self, *, admin_project_id: str):
        # Default security group
        self.create_security_group(
            name="default",
            tenant_id=admin_project_id,
            description="Default security group",
        )

        # Public external network + subnet
        pub_net = self.create_network(
            name="public",
            tenant_id=admin_project_id,
            shared=True,
            external=True,
        )
        self.create_subnet(
            name="public-subnet",
            network_id=pub_net.id,
            cidr="10.0.0.0/24",
            tenant_id=admin_project_id,
        )

        # Private internal network + subnet
        priv_net = self.create_network(
            name="private",
            tenant_id=admin_project_id,
        )
        self.create_subnet(
            name="private-subnet",
            network_id=priv_net.id,
            cidr="192.168.1.0/24",
            tenant_id=admin_project_id,
        )
