from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class Domain:
    id: str
    name: str
    enabled: bool = True


@dataclass
class Project:
    id: str
    name: str
    domain_id: str
    enabled: bool = True
    description: str = ""


@dataclass
class User:
    id: str
    name: str
    password: str
    domain_id: str
    enabled: bool = True
    default_project_id: Optional[str] = None


@dataclass
class Role:
    id: str
    name: str


@dataclass
class RoleAssignment:
    user_id: str
    project_id: str
    role_id: str


@dataclass
class Service:
    id: str
    type: str
    name: str
    enabled: bool = True


@dataclass
class Endpoint:
    id: str
    service_id: str
    interface: str  # public / internal / admin
    url: str
    region: str


@dataclass
class Token:
    id: str
    user_id: str
    project_id: Optional[str]
    roles: list[dict]
    issued_at: datetime
    expires_at: datetime
    catalog: list[dict]
    methods: list[str] = field(default_factory=lambda: ["password"])


class KeystoneStore:
    def __init__(self):
        self.domains: dict[str, Domain] = {}
        self.projects: dict[str, Project] = {}
        self.users: dict[str, User] = {}
        self.roles: dict[str, Role] = {}
        self.role_assignments: list[RoleAssignment] = []
        self.services: dict[str, Service] = {}
        self.endpoints: dict[str, Endpoint] = {}
        self.tokens: dict[str, Token] = {}

    # ── helpers ──────────────────────────────────────────

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    def find_user_by_name(self, name: str, domain_id: str) -> Optional[User]:
        for u in self.users.values():
            if u.name == name and u.domain_id == domain_id:
                return u
        return None

    def find_project_by_name(self, name: str, domain_id: str) -> Optional[Project]:
        for p in self.projects.values():
            if p.name == name and p.domain_id == domain_id:
                return p
        return None

    def get_roles_for_user_project(self, user_id: str, project_id: str) -> list[Role]:
        role_ids = [
            ra.role_id
            for ra in self.role_assignments
            if ra.user_id == user_id and ra.project_id == project_id
        ]
        return [self.roles[rid] for rid in role_ids if rid in self.roles]

    def build_catalog(self) -> list[dict]:
        catalog: dict[str, dict] = {}
        for svc in self.services.values():
            catalog[svc.id] = {
                "type": svc.type,
                "name": svc.name,
                "id": svc.id,
                "endpoints": [],
            }
        for ep in self.endpoints.values():
            if ep.service_id in catalog:
                catalog[ep.service_id]["endpoints"].append(
                    {
                        "id": ep.id,
                        "interface": ep.interface,
                        "url": ep.url,
                        "region": ep.region,
                        "region_id": ep.region,
                    }
                )
        return list(catalog.values())

    # ── token operations ─────────────────────────────────

    def issue_token(self, user: User, project: Optional[Project]) -> Token:
        roles = (
            self.get_roles_for_user_project(user.id, project.id) if project else []
        )
        now = datetime.now(timezone.utc)
        token = Token(
            id=self._uuid(),
            user_id=user.id,
            project_id=project.id if project else None,
            roles=[{"id": r.id, "name": r.name} for r in roles],
            issued_at=now,
            expires_at=now + timedelta(hours=1),
            catalog=self.build_catalog(),
        )
        self.tokens[token.id] = token
        return token

    def validate_token(self, token_id: str) -> Optional[Token]:
        token = self.tokens.get(token_id)
        if token is None:
            return None
        if token.expires_at < datetime.now(timezone.utc):
            del self.tokens[token_id]
            return None
        return token

    def revoke_token(self, token_id: str) -> bool:
        return self.tokens.pop(token_id, None) is not None

    # ── bootstrap ────────────────────────────────────────

    def bootstrap(
        self,
        *,
        admin_username: str = "admin",
        admin_password: str = "password",
        admin_project: str = "admin",
        region: str = "RegionOne",
        endpoint_host: str = "localhost",
        keystone_port: int = 5000,
        nova_port: int = 8774,
        neutron_port: int = 9696,
        glance_port: int = 9292,
    ):
        # domain
        domain = Domain(id="default", name="Default", enabled=True)
        self.domains[domain.id] = domain

        # project
        proj = Project(
            id=self._uuid(),
            name=admin_project,
            domain_id=domain.id,
        )
        self.projects[proj.id] = proj

        # user
        user = User(
            id=self._uuid(),
            name=admin_username,
            password=admin_password,
            domain_id=domain.id,
            default_project_id=proj.id,
        )
        self.users[user.id] = user

        # roles
        admin_role = Role(id=self._uuid(), name="admin")
        member_role = Role(id=self._uuid(), name="member")
        reader_role = Role(id=self._uuid(), name="reader")
        for r in (admin_role, member_role, reader_role):
            self.roles[r.id] = r

        # role assignments
        self.role_assignments.append(
            RoleAssignment(user_id=user.id, project_id=proj.id, role_id=admin_role.id)
        )
        self.role_assignments.append(
            RoleAssignment(user_id=user.id, project_id=proj.id, role_id=member_role.id)
        )

        # services + endpoints
        base = f"http://{endpoint_host}"
        service_defs = [
            ("identity", "keystone", f"{base}:{keystone_port}/v3"),
            ("compute", "nova", f"{base}:{nova_port}/v2.1"),
            ("network", "neutron", f"{base}:{neutron_port}"),
            ("image", "glance", f"{base}:{glance_port}"),
        ]
        for stype, sname, url in service_defs:
            svc = Service(id=self._uuid(), type=stype, name=sname)
            self.services[svc.id] = svc
            for iface in ("public", "internal", "admin"):
                ep = Endpoint(
                    id=self._uuid(),
                    service_id=svc.id,
                    interface=iface,
                    url=url,
                    region=region,
                )
                self.endpoints[ep.id] = ep
