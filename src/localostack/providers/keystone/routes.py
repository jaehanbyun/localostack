from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from .models import AuthRequest, RoleCreateRequest, ProjectCreateRequest, ProjectUpdateRequest, UserCreateRequest, UserUpdateRequest
from .store import KeystoneStore, User, Project, Role, RoleAssignment


router = APIRouter()


_HTTP_TITLES = {400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 409: "Conflict"}


def _error(code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": {"message": message, "code": code, "title": _HTTP_TITLES.get(code, "Error")}},
    )


def _get_store(request: Request) -> KeystoneStore:
    return request.app.state.keystone_store


class _AuthError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_id = auth_header[7:]
    if not token_id:
        raise _AuthError(_error(401, "The request you have made requires authentication."))
    return token_id


# ── Tokens ───────────────────────────────────────────────

@router.post("/v3/auth/tokens", status_code=201)
async def create_token(body: AuthRequest, request: Request):
    store = _get_store(request)
    auth = body.auth
    identity = auth.identity

    if "password" not in identity.methods or identity.password is None:
        return _error(400, "Only password authentication is supported")

    pw = identity.password
    user_info = pw.user
    domain_id = "default"
    if user_info.domain and user_info.domain.id:
        domain_id = user_info.domain.id

    if user_info.id:
        user = store.users.get(user_info.id)
    else:
        user = store.find_user_by_name(user_info.name or "", domain_id)

    if user is None or user.password != user_info.password:
        return _error(401, "Invalid credentials")

    if not user.enabled:
        return _error(401, "User is disabled")

    project = None
    if auth.scope and auth.scope.project:
        sp = auth.scope.project
        scope_domain_id = "default"
        if sp.domain and sp.domain.id:
            scope_domain_id = sp.domain.id
        if sp.id:
            project = store.projects.get(sp.id)
        else:
            project = store.find_project_by_name(sp.name or "", scope_domain_id)
        if project is None:
            return _error(401, "Could not find project")

    token = store.issue_token(user, project)

    domain = store.domains.get(user.domain_id)
    user_body = {
        "id": user.id,
        "name": user.name,
        "domain": {"id": domain.id, "name": domain.name} if domain else {"id": user.domain_id},
    }
    project_body = None
    if project:
        proj_domain = store.domains.get(project.domain_id)
        project_body = {
            "id": project.id,
            "name": project.name,
            "domain": {"id": proj_domain.id, "name": proj_domain.name} if proj_domain else {"id": project.domain_id},
        }

    response_body = {
        "token": {
            "methods": token.methods,
            "user": user_body,
            "roles": token.roles,
            "catalog": token.catalog,
            "issued_at": token.issued_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "expires_at": token.expires_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
    }
    if project_body:
        response_body["token"]["project"] = project_body

    return JSONResponse(
        status_code=201,
        content=response_body,
        headers={"X-Subject-Token": token.id},
    )


@router.get("/v3/auth/tokens")
async def validate_token(request: Request):
    _require_token(request)
    store = _get_store(request)
    subject_token_id = request.headers.get("X-Subject-Token")
    if not subject_token_id:
        return _error(400, "Missing X-Subject-Token header")

    token = store.validate_token(subject_token_id)
    if token is None:
        return _error(404, "Token not found")

    user = store.users.get(token.user_id)
    domain = store.domains.get(user.domain_id) if user else None
    user_body = {
        "id": user.id,
        "name": user.name,
        "domain": {"id": domain.id, "name": domain.name} if domain else {},
    } if user else {}

    project_body = None
    if token.project_id:
        project = store.projects.get(token.project_id)
        if project:
            proj_domain = store.domains.get(project.domain_id)
            project_body = {
                "id": project.id,
                "name": project.name,
                "domain": {"id": proj_domain.id, "name": proj_domain.name} if proj_domain else {"id": project.domain_id},
            }

    body: dict = {
        "token": {
            "methods": token.methods,
            "user": user_body,
            "roles": token.roles,
            "catalog": token.catalog,
            "issued_at": token.issued_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "expires_at": token.expires_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        }
    }
    if project_body:
        body["token"]["project"] = project_body

    return JSONResponse(
        content=body,
        headers={"X-Subject-Token": subject_token_id},
    )


@router.head("/v3/auth/tokens")
async def check_token(request: Request):
    _require_token(request)
    store = _get_store(request)
    subject_token_id = request.headers.get("X-Subject-Token")
    if not subject_token_id:
        return Response(status_code=400)
    token = store.validate_token(subject_token_id)
    if token is None:
        return Response(status_code=404)
    return Response(status_code=204)


@router.delete("/v3/auth/tokens")
async def revoke_token(request: Request):
    _require_token(request)
    store = _get_store(request)
    subject_token_id = request.headers.get("X-Subject-Token")
    if not subject_token_id:
        return _error(400, "Missing X-Subject-Token header")
    if not store.revoke_token(subject_token_id):
        return _error(404, "Token not found")
    return Response(status_code=204)


# ── Catalog ──────────────────────────────────────────────

@router.get("/v3/auth/catalog")
async def get_catalog(request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"catalog": store.build_catalog()}


@router.get("/v3/auth/projects")
async def get_auth_projects(request: Request):
    token_id = _require_token(request)
    store = _get_store(request)
    token = store.tokens.get(token_id) if token_id else None
    projects = [
        {"id": p.id, "name": p.name, "domain_id": p.domain_id, "enabled": p.enabled}
        for p in store.projects.values()
        if p.enabled
    ]
    return {"projects": projects}


@router.get("/v3/auth/domains")
async def get_auth_domains(request: Request):
    _require_token(request)
    store = _get_store(request)
    domains = [
        {"id": d.id, "name": d.name, "enabled": d.enabled}
        for d in store.domains.values()
    ]
    return {"domains": domains}


# ── Users ────────────────────────────────────────────────

@router.get("/v3/users")
async def list_users(request: Request):
    _require_token(request)
    store = _get_store(request)
    users = [
        {"id": u.id, "name": u.name, "domain_id": u.domain_id, "enabled": u.enabled, "default_project_id": u.default_project_id}
        for u in store.users.values()
    ]
    return {"users": users}


@router.post("/v3/users", status_code=201)
async def create_user(body: UserCreateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    data = body.user
    name = data.get("name")
    if not name:
        return _error(400, "User name is required")
    domain_id = data.get("domain_id", "default")
    if store.find_user_by_name(name, domain_id):
        return _error(409, f"User {name} already exists")
    user = User(
        id=store._uuid(),
        name=name,
        password=data.get("password", ""),
        domain_id=domain_id,
        enabled=data.get("enabled", True),
        default_project_id=data.get("default_project_id"),
    )
    store.users[user.id] = user
    return {"user": {"id": user.id, "name": user.name, "domain_id": user.domain_id, "enabled": user.enabled, "default_project_id": user.default_project_id}}


@router.get("/v3/users/{user_id}")
async def get_user(user_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    user = store.users.get(user_id)
    if not user:
        return _error(404, "User not found")
    return {"user": {"id": user.id, "name": user.name, "domain_id": user.domain_id, "enabled": user.enabled, "default_project_id": user.default_project_id}}


@router.patch("/v3/users/{user_id}")
async def update_user(user_id: str, body: UserUpdateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    user = store.users.get(user_id)
    if not user:
        return _error(404, "User not found")
    data = body.user
    if "name" in data:
        user.name = data["name"]
    if "password" in data:
        user.password = data["password"]
    if "enabled" in data:
        user.enabled = data["enabled"]
    if "default_project_id" in data:
        user.default_project_id = data["default_project_id"]
    return {"user": {"id": user.id, "name": user.name, "domain_id": user.domain_id, "enabled": user.enabled, "default_project_id": user.default_project_id}}


@router.delete("/v3/users/{user_id}")
async def delete_user(user_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if user_id not in store.users:
        return _error(404, "User not found")
    del store.users[user_id]
    return Response(status_code=204)


# ── Projects ─────────────────────────────────────────────

@router.get("/v3/projects")
async def list_projects(request: Request):
    _require_token(request)
    store = _get_store(request)
    projects = [
        {"id": p.id, "name": p.name, "domain_id": p.domain_id, "enabled": p.enabled, "description": p.description}
        for p in store.projects.values()
    ]
    return {"projects": projects}


@router.post("/v3/projects", status_code=201)
async def create_project(body: ProjectCreateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    data = body.project
    name = data.get("name")
    if not name:
        return _error(400, "Project name is required")
    domain_id = data.get("domain_id", "default")
    if store.find_project_by_name(name, domain_id):
        return _error(409, f"Project {name} already exists")
    proj = Project(
        id=store._uuid(),
        name=name,
        domain_id=domain_id,
        enabled=data.get("enabled", True),
        description=data.get("description", ""),
    )
    store.projects[proj.id] = proj
    return {"project": {"id": proj.id, "name": proj.name, "domain_id": proj.domain_id, "enabled": proj.enabled, "description": proj.description}}


@router.get("/v3/projects/{project_id}")
async def get_project(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    proj = store.projects.get(project_id)
    if not proj:
        return _error(404, "Project not found")
    return {"project": {"id": proj.id, "name": proj.name, "domain_id": proj.domain_id, "enabled": proj.enabled, "description": proj.description}}


@router.patch("/v3/projects/{project_id}")
async def update_project(project_id: str, body: ProjectUpdateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    proj = store.projects.get(project_id)
    if not proj:
        return _error(404, "Project not found")
    data = body.project
    if "name" in data:
        proj.name = data["name"]
    if "enabled" in data:
        proj.enabled = data["enabled"]
    if "description" in data:
        proj.description = data["description"]
    return {"project": {"id": proj.id, "name": proj.name, "domain_id": proj.domain_id, "enabled": proj.enabled, "description": proj.description}}


@router.delete("/v3/projects/{project_id}")
async def delete_project(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if project_id not in store.projects:
        return _error(404, "Project not found")
    del store.projects[project_id]
    return Response(status_code=204)


# ── Roles ────────────────────────────────────────────────

@router.get("/v3/roles")
async def list_roles(request: Request):
    _require_token(request)
    store = _get_store(request)
    roles = [{"id": r.id, "name": r.name} for r in store.roles.values()]
    return {"roles": roles}


@router.post("/v3/roles", status_code=201)
async def create_role(body: RoleCreateRequest, request: Request):
    _require_token(request)
    store = _get_store(request)
    data = body.role
    name = data.get("name")
    if not name:
        return _error(400, "Role name is required")
    for r in store.roles.values():
        if r.name == name:
            return _error(409, f"Role {name} already exists")
    role = Role(id=store._uuid(), name=name)
    store.roles[role.id] = role
    return {"role": {"id": role.id, "name": role.name}}


@router.get("/v3/roles/{role_id}")
async def get_role(role_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    role = store.roles.get(role_id)
    if not role:
        return _error(404, "Role not found")
    return {"role": {"id": role.id, "name": role.name}}


# ── Role assignments ─────────────────────────────────────

@router.put("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}", status_code=204)
async def assign_role(project_id: str, user_id: str, role_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if project_id not in store.projects:
        return _error(404, "Project not found")
    if user_id not in store.users:
        return _error(404, "User not found")
    if role_id not in store.roles:
        return _error(404, "Role not found")
    for ra in store.role_assignments:
        if ra.user_id == user_id and ra.project_id == project_id and ra.role_id == role_id:
            return Response(status_code=204)
    store.role_assignments.append(RoleAssignment(user_id=user_id, project_id=project_id, role_id=role_id))
    return Response(status_code=204)


@router.delete("/v3/projects/{project_id}/users/{user_id}/roles/{role_id}", status_code=204)
async def unassign_role(project_id: str, user_id: str, role_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    for i, ra in enumerate(store.role_assignments):
        if ra.user_id == user_id and ra.project_id == project_id and ra.role_id == role_id:
            store.role_assignments.pop(i)
            return Response(status_code=204)
    return _error(404, "Role assignment not found")


@router.get("/v3/role_assignments")
async def list_role_assignments(request: Request):
    _require_token(request)
    store = _get_store(request)
    user_id = request.query_params.get("user.id")
    project_id = request.query_params.get("scope.project.id")
    assignments = store.role_assignments
    if user_id:
        assignments = [ra for ra in assignments if ra.user_id == user_id]
    if project_id:
        assignments = [ra for ra in assignments if ra.project_id == project_id]
    result = []
    for ra in assignments:
        role = store.roles.get(ra.role_id)
        result.append({
            "role": {"id": ra.role_id, "name": role.name if role else ""},
            "user": {"id": ra.user_id},
            "scope": {"project": {"id": ra.project_id}},
        })
    return {"role_assignments": result}


# ── Services / Endpoints ────────────────────────────────

@router.get("/v3/services")
async def list_services(request: Request):
    _require_token(request)
    store = _get_store(request)
    services = [
        {"id": s.id, "type": s.type, "name": s.name, "enabled": s.enabled}
        for s in store.services.values()
    ]
    return {"services": services}


@router.get("/v3/endpoints")
async def list_endpoints(request: Request):
    _require_token(request)
    store = _get_store(request)
    endpoints = [
        {"id": e.id, "service_id": e.service_id, "interface": e.interface, "url": e.url, "region": e.region, "region_id": e.region}
        for e in store.endpoints.values()
    ]
    return {"endpoints": endpoints}


# ── Domains ──────────────────────────────────────────────

@router.get("/v3/domains")
async def list_domains(request: Request):
    _require_token(request)
    store = _get_store(request)
    domains = [{"id": d.id, "name": d.name, "enabled": d.enabled} for d in store.domains.values()]
    return {"domains": domains}


@router.get("/v3/domains/{domain_id}")
async def get_domain(domain_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    domain = store.domains.get(domain_id)
    if not domain:
        return _error(404, "Domain not found")
    return {"domain": {"id": domain.id, "name": domain.name, "enabled": domain.enabled}}


# ── Groups ───────────────────────────────────────────────

@router.get("/v3/groups")
async def list_groups(request: Request):
    _require_token(request)
    return {"groups": []}


@router.get("/v3/groups/{group_id}")
async def get_group(group_id: str, request: Request):
    _require_token(request)
    return _error(404, "Group not found")


@router.get("/v3/groups/{group_id}/users")
async def list_group_users(group_id: str, request: Request):
    _require_token(request)
    return {"users": []}


# ── Application Credentials ──────────────────────────────

@router.get("/v3/users/{user_id}/application_credentials")
async def list_application_credentials(user_id: str, request: Request):
    _require_token(request)
    return {"application_credentials": []}


# ── Registered Limits ─────────────────────────────────────

@router.get("/v3/registered_limits")
async def list_registered_limits(request: Request):
    _require_token(request)
    return {"registered_limits": []}


@router.get("/v3/limits")
async def list_limits(request: Request):
    _require_token(request)
    return {"limits": []}


# ── Credentials ──────────────────────────────────────────

@router.get("/v3/credentials")
async def list_credentials(request: Request):
    _require_token(request)
    return {"credentials": []}


# ── Regions ──────────────────────────────────────────────

@router.get("/v3/regions")
async def list_regions(request: Request):
    _require_token(request)
    return {
        "regions": [
            {"id": "RegionOne", "description": "", "parent_region_id": None, "links": {}}
        ]
    }
