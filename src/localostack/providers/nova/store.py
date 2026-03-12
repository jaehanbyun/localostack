"""Nova in-memory store."""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .state_machine import get_status, transition


@dataclass
class Server:
    id: str
    name: str
    tenant_id: str = ""
    user_id: str = ""
    image_ref: str = ""
    flavor_id: str = ""
    status: str = "BUILD"
    vm_state: str = "building"
    task_state: Optional[str] = None
    power_state: int = 0
    key_name: Optional[str] = None
    security_groups: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    addresses: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    host: str = "localostack"
    availability_zone: str = "nova"
    volumes_attached: list[dict] = field(default_factory=list)


@dataclass
class Flavor:
    id: str
    name: str
    vcpus: int = 1
    ram: int = 512
    disk: int = 1
    ephemeral: int = 0
    swap: str = ""
    rxtx_factor: float = 1.0
    is_public: bool = True


@dataclass
class Keypair:
    id: str
    name: str
    user_id: str = ""
    public_key: str = ""
    fingerprint: str = ""
    type: str = "ssh"
    created_at: str = ""


class NovaStore:
    def __init__(self, backend=None):
        self._b = backend
        self.servers: dict[str, Server] = {}
        self.flavors: dict[str, Flavor] = {}
        self.keypairs: dict[str, Keypair] = {}

    def _save(self, rtype: str, id: str, obj) -> None:
        if self._b:
            self._b.put("nova", rtype, id, asdict(obj))

    def _del(self, rtype: str, id: str) -> None:
        if self._b:
            self._b.delete("nova", rtype, id)

    def _load_persisted(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("nova", "servers"):
            srv = Server(**data)
            self.servers[srv.id] = srv
        for data in self._b.get_all("nova", "flavors"):
            f = Flavor(**data)
            self.flavors[f.id] = f
        for data in self._b.get_all("nova", "keypairs"):
            kp = Keypair(**data)
            self.keypairs[kp.id] = kp

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

    @staticmethod
    def _generate_ip() -> str:
        return "192.168.1.{}".format(random.randint(2, 254))

    @staticmethod
    def _generate_fingerprint() -> str:
        parts = ["{:02x}".format(random.randint(0, 255)) for _ in range(16)]
        return ":".join(parts)

    # ── Flavor helpers ────────────────────────────────────

    def find_flavor(self, flavor_ref: str) -> Optional[Flavor]:
        """id 또는 name으로 플레이버를 찾는다."""
        flavor = self.flavors.get(flavor_ref)
        if flavor is not None:
            return flavor
        for f in self.flavors.values():
            if f.name == flavor_ref:
                return f
        return None

    # ── Server CRUD ───────────────────────────────────────

    def create_server(
        self,
        *,
        name: str,
        tenant_id: str = "",
        user_id: str = "",
        image_ref: str = "",
        flavor_ref: str = "",
        key_name: Optional[str] = None,
        security_groups: Optional[list[dict]] = None,
        networks: Optional[list[dict]] = None,
        metadata: Optional[dict] = None,
    ) -> Server:
        now = self._now()

        # 플레이버 결정
        flavor = self.find_flavor(flavor_ref)
        flavor_id = flavor.id if flavor else flavor_ref

        # security_groups 기본값
        if security_groups is None:
            security_groups = [{"name": "default"}]

        # addresses 구성 ("none"/"auto" 문자열은 빈 네트워크로 처리)
        addresses: dict = {}
        if networks and isinstance(networks, list):
            for net_info in networks:
                network_name = net_info.get("uuid", "private")
                addresses[network_name] = [
                    {
                        "addr": self._generate_ip(),
                        "version": 4,
                        "OS-EXT-IPS:type": "fixed",
                        "OS-EXT-IPS-MAC:mac_addr": self._generate_mac(),
                    }
                ]

        # 상태 전이 (create)
        result = transition(None, "create")
        vm_state, task_state, power_state = result if result else ("active", None, 1)

        server = Server(
            id=self._uuid(),
            name=name,
            tenant_id=tenant_id,
            user_id=user_id,
            image_ref=image_ref,
            flavor_id=flavor_id,
            status=get_status(vm_state, task_state),
            vm_state=vm_state,
            task_state=task_state,
            power_state=power_state,
            key_name=key_name,
            security_groups=security_groups,
            metadata=metadata or {},
            addresses=addresses,
            created_at=now,
            updated_at=now,
        )
        self.servers[server.id] = server
        self._save("servers", server.id, server)
        return server

    def get_server(self, server_id: str) -> Optional[Server]:
        return self.servers.get(server_id)

    def list_servers(self, tenant_id: Optional[str] = None) -> list[Server]:
        result = []
        for srv in self.servers.values():
            if srv.status == "DELETED":
                continue
            if tenant_id and srv.tenant_id != tenant_id:
                continue
            result.append(srv)
        return result

    def update_server(self, server_id: str, **kwargs) -> Optional[Server]:
        srv = self.get_server(server_id)
        if srv is None or srv.status == "DELETED":
            return None
        for key, value in kwargs.items():
            if hasattr(srv, key) and key not in ("id", "created_at"):
                setattr(srv, key, value)
        srv.updated_at = self._now()
        self._save("servers", srv.id, srv)
        return srv

    def delete_server(self, server_id: str) -> bool:
        srv = self.servers.get(server_id)
        if srv is None or srv.status == "DELETED":
            return False
        result = transition(srv.vm_state, "delete")
        if result is None:
            return False
        srv.vm_state, srv.task_state, srv.power_state = result
        srv.status = get_status(srv.vm_state, srv.task_state)
        srv.updated_at = self._now()
        self._del("servers", server_id)
        return True

    # ── Server Actions ────────────────────────────────────

    def server_action(self, server_id: str, action: str) -> Optional[Server]:
        srv = self.servers.get(server_id)
        if srv is None or srv.status == "DELETED":
            return None
        result = transition(srv.vm_state, action)
        if result is None:
            return None
        srv.vm_state, srv.task_state, srv.power_state = result
        srv.status = get_status(srv.vm_state, srv.task_state)
        srv.updated_at = self._now()
        self._save("servers", srv.id, srv)
        return srv

    # ── Flavor CRUD ───────────────────────────────────────

    def create_flavor(
        self,
        *,
        name: str,
        vcpus: int = 1,
        ram: int = 512,
        disk: int = 1,
        ephemeral: int = 0,
        swap: str = "",
        rxtx_factor: float = 1.0,
        is_public: bool = True,
        id: Optional[str] = None,
    ) -> Flavor:
        flavor = Flavor(
            id=id or self._uuid(),
            name=name,
            vcpus=vcpus,
            ram=ram,
            disk=disk,
            ephemeral=ephemeral,
            swap=swap,
            rxtx_factor=rxtx_factor,
            is_public=is_public,
        )
        self.flavors[flavor.id] = flavor
        self._save("flavors", flavor.id, flavor)
        return flavor

    def get_flavor(self, flavor_id: str) -> Optional[Flavor]:
        return self.flavors.get(flavor_id)

    def list_flavors(self) -> list[Flavor]:
        return list(self.flavors.values())

    # ── Keypair CRUD ──────────────────────────────────────

    def create_keypair(
        self,
        *,
        name: str,
        user_id: str = "",
        public_key: Optional[str] = None,
        type: str = "ssh",
    ) -> Keypair:
        now = self._now()
        kp = Keypair(
            id=self._uuid(),
            name=name,
            user_id=user_id,
            public_key=public_key or "",
            fingerprint=self._generate_fingerprint(),
            type=type,
            created_at=now,
        )
        self.keypairs[kp.id] = kp
        self._save("keypairs", kp.id, kp)
        return kp

    def get_keypair(self, name: str) -> Optional[Keypair]:
        for kp in self.keypairs.values():
            if kp.name == name:
                return kp
        return None

    def list_keypairs(self, user_id: Optional[str] = None) -> list[Keypair]:
        result = []
        for kp in self.keypairs.values():
            if user_id and kp.user_id != user_id:
                continue
            result.append(kp)
        return result

    def delete_keypair(self, name: str) -> bool:
        for kp_id, kp in self.keypairs.items():
            if kp.name == name:
                del self.keypairs[kp_id]
                self._del("keypairs", kp_id)
                return True
        return False

    # ── Bootstrap ─────────────────────────────────────────

    def bootstrap(self):
        """표준 플레이버를 등록한다."""
        self._load_persisted()
        if not self.flavors:
            standard_flavors = [
                {"id": "1", "name": "m1.tiny", "vcpus": 1, "ram": 512, "disk": 1},
                {"id": "2", "name": "m1.small", "vcpus": 1, "ram": 2048, "disk": 20},
                {"id": "3", "name": "m1.medium", "vcpus": 2, "ram": 4096, "disk": 40},
                {"id": "4", "name": "m1.large", "vcpus": 4, "ram": 8192, "disk": 80},
                {"id": "5", "name": "m1.xlarge", "vcpus": 8, "ram": 16384, "disk": 160},
            ]
            for f in standard_flavors:
                self.create_flavor(**f)
