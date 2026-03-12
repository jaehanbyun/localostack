from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Auth request models ──────────────────────────────────

class PasswordUserDomain(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class PasswordUser(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    domain: Optional[PasswordUserDomain] = None
    password: str


class PasswordIdentity(BaseModel):
    user: PasswordUser


class Identity(BaseModel):
    methods: list[str]
    password: Optional[PasswordIdentity] = None


class ScopeProjectDomain(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None


class ScopeProject(BaseModel):
    name: Optional[str] = None
    id: Optional[str] = None
    domain: Optional[ScopeProjectDomain] = None


class Scope(BaseModel):
    project: Optional[ScopeProject] = None


class Auth(BaseModel):
    identity: Identity
    scope: Optional[Scope] = None


class AuthRequest(BaseModel):
    auth: Auth


# ── Response models ──────────────────────────────────────

class DomainRef(BaseModel):
    id: str
    name: str


class UserResponse(BaseModel):
    id: str
    name: str
    domain_id: str
    enabled: bool = True
    default_project_id: Optional[str] = None


class ProjectResponse(BaseModel):
    id: str
    name: str
    domain_id: str
    enabled: bool = True
    description: str = ""


class RoleResponse(BaseModel):
    id: str
    name: str


class ServiceResponse(BaseModel):
    id: str
    type: str
    name: str
    enabled: bool = True


class EndpointResponse(BaseModel):
    id: str
    service_id: str
    interface: str
    url: str
    region: str
    region_id: str


class TokenResponse(BaseModel):
    methods: list[str]
    user: dict[str, Any]
    roles: list[dict[str, Any]]
    catalog: list[dict[str, Any]]
    project: Optional[dict[str, Any]] = None
    issued_at: str
    expires_at: str


# ── Create / Update request models ──────────────────────

class UserCreateRequest(BaseModel):
    user: dict[str, Any]


class UserUpdateRequest(BaseModel):
    user: dict[str, Any]


class ProjectCreateRequest(BaseModel):
    project: dict[str, Any]


class ProjectUpdateRequest(BaseModel):
    project: dict[str, Any]


class RoleCreateRequest(BaseModel):
    role: dict[str, Any]
