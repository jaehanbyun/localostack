"""Cinder API routes."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from .store import CinderStore

router = APIRouter()


def _error(code: int, key: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={key: {"message": message, "code": code}},
    )


def _get_store(request: Request) -> CinderStore:
    return request.app.state.cinder_store


def _require_token(request: Request) -> str:
    token_id = request.headers.get("X-Auth-Token")
    if not token_id:
        raise _AuthError(_error(401, "error", "Authentication required"))
    return token_id


class _AuthError(Exception):
    def __init__(self, response: JSONResponse):
        self.response = response


# ── Serializers ───────────────────────────────────────────

def _volume_brief(vol) -> dict:
    return {
        "id": vol.id,
        "name": vol.name,
        "links": [
            {"rel": "self", "href": f"/v3/volumes/{vol.id}"},
            {"rel": "bookmark", "href": f"/volumes/{vol.id}"},
        ],
    }


def _volume_detail(vol) -> dict:
    return {
        "id": vol.id,
        "name": vol.name,
        "status": vol.status,
        "size": vol.size,
        "volume_type": vol.volume_type,
        "availability_zone": vol.availability_zone,
        "bootable": str(vol.bootable).lower(),
        "encrypted": vol.encrypted,
        "description": vol.description,
        "metadata": vol.metadata,
        "attachments": vol.attachments,
        "tenant_id": vol.tenant_id,
        "user_id": vol.user_id,
        "created_at": vol.created_at,
        "updated_at": vol.updated_at,
        "snapshot_id": vol.snapshot_id,
        "source_volid": vol.source_volid,
        "links": [
            {"rel": "self", "href": f"/v3/volumes/{vol.id}"},
            {"rel": "bookmark", "href": f"/volumes/{vol.id}"},
        ],
    }


def _snapshot_detail(snap) -> dict:
    return {
        "id": snap.id,
        "name": snap.name,
        "volume_id": snap.volume_id,
        "size": snap.size,
        "status": snap.status,
        "description": snap.description,
        "metadata": snap.metadata,
        "created_at": snap.created_at,
        "updated_at": snap.updated_at,
    }


def _volume_type_detail(vt) -> dict:
    return {
        "id": vt.id,
        "name": vt.name,
        "description": vt.description,
        "is_public": vt.is_public,
        "extra_specs": vt.extra_specs,
    }


# ── Volume endpoints ──────────────────────────────────────

@router.get("/v3/{project_id}/volumes")
async def list_volumes(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"volumes": [_volume_brief(v) for v in store.list_volumes()]}


@router.get("/v3/{project_id}/volumes/detail")
async def list_volumes_detail(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"volumes": [_volume_detail(v) for v in store.list_volumes()]}


@router.post("/v3/{project_id}/volumes", status_code=202)
async def create_volume(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    token_id = request.headers.get("X-Auth-Token", "")
    body = await request.json()
    data = body.get("volume", body)
    vol = store.create_volume(
        name=data.get("name", ""),
        size=data.get("size", 1),
        volume_type=data.get("volume_type", ""),
        availability_zone=data.get("availability_zone", "nova"),
        description=data.get("description", ""),
        metadata=data.get("metadata"),
        snapshot_id=data.get("snapshot_id"),
        source_volid=data.get("source_volid"),
        tenant_id=project_id,
        user_id=token_id,
    )
    return JSONResponse(status_code=202, content={"volume": _volume_detail(vol)})


@router.get("/v3/{project_id}/volumes/{volume_id}")
async def get_volume(project_id: str, volume_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    vol = store.get_volume(volume_id)
    if vol is None:
        return _error(404, "itemNotFound", "Volume not found")
    return {"volume": _volume_detail(vol)}


@router.put("/v3/{project_id}/volumes/{volume_id}")
async def update_volume(project_id: str, volume_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    vol = store.get_volume(volume_id)
    if vol is None:
        return _error(404, "itemNotFound", "Volume not found")
    body = await request.json()
    data = body.get("volume", body)
    updates = {}
    for field in ("name", "description", "metadata"):
        if field in data:
            updates[field] = data[field]
    vol = store.update_volume(volume_id, **updates)
    return {"volume": _volume_detail(vol)}


@router.delete("/v3/{project_id}/volumes/{volume_id}")
async def delete_volume(project_id: str, volume_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_volume(volume_id):
        return _error(404, "itemNotFound", "Volume not found")
    return Response(status_code=204)


# ── Snapshot endpoints ────────────────────────────────────

@router.get("/v3/{project_id}/snapshots")
async def list_snapshots(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"snapshots": [_snapshot_detail(s) for s in store.list_snapshots()]}


@router.get("/v3/{project_id}/snapshots/detail")
async def list_snapshots_detail(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"snapshots": [_snapshot_detail(s) for s in store.list_snapshots()]}


@router.post("/v3/{project_id}/snapshots", status_code=202)
async def create_snapshot(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    body = await request.json()
    data = body.get("snapshot", body)
    snap = store.create_snapshot(
        name=data.get("name", ""),
        volume_id=data.get("volume_id", ""),
        description=data.get("description", ""),
        metadata=data.get("metadata"),
        tenant_id=project_id,
    )
    return JSONResponse(status_code=202, content={"snapshot": _snapshot_detail(snap)})


@router.get("/v3/{project_id}/snapshots/{snapshot_id}")
async def get_snapshot(project_id: str, snapshot_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    snap = store.get_snapshot(snapshot_id)
    if snap is None:
        return _error(404, "itemNotFound", "Snapshot not found")
    return {"snapshot": _snapshot_detail(snap)}


@router.delete("/v3/{project_id}/snapshots/{snapshot_id}")
async def delete_snapshot(project_id: str, snapshot_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    if not store.delete_snapshot(snapshot_id):
        return _error(404, "itemNotFound", "Snapshot not found")
    return Response(status_code=204)


# ── VolumeType endpoints ──────────────────────────────────

@router.get("/v3/{project_id}/types")
async def list_volume_types(project_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    return {"volume_types": [_volume_type_detail(vt) for vt in store.list_volume_types()]}


@router.get("/v3/{project_id}/types/{type_id}")
async def get_volume_type(project_id: str, type_id: str, request: Request):
    _require_token(request)
    store = _get_store(request)
    vt = store.get_volume_type(type_id)
    if vt is None:
        return _error(404, "itemNotFound", "VolumeType not found")
    return {"volume_type": _volume_type_detail(vt)}


# ── Backups ───────────────────────────────────────────────

@router.get("/v3/{project_id}/backups")
async def list_backups(project_id: str, request: Request):
    _require_token(request)
    return {"backups": []}


@router.get("/v3/{project_id}/backups/detail")
async def list_backups_detail(project_id: str, request: Request):
    _require_token(request)
    return {"backups": []}


# ── Availability Zones ────────────────────────────────────

@router.get("/v3/{project_id}/os-availability-zone")
async def list_cinder_availability_zones(project_id: str, request: Request):
    _require_token(request)
    return {
        "availabilityZoneInfo": [
            {"zoneName": "nova", "zoneState": {"available": True}}
        ]
    }


# ── Quota Sets ────────────────────────────────────────────

_DEFAULT_CINDER_QUOTA = {
    "gigabytes": 1000, "snapshots": 10, "volumes": 10,
    "backups": 10, "backup_gigabytes": 1000,
    "per_volume_gigabytes": -1,
}


@router.get("/v3/{project_id}/os-quota-sets/{target_project_id}")
async def get_cinder_quota_sets(project_id: str, target_project_id: str, request: Request):
    _require_token(request)
    return {"quota_set": {**_DEFAULT_CINDER_QUOTA, "id": target_project_id}}


@router.get("/v3/{project_id}/os-quota-sets/{target_project_id}/detail")
async def get_cinder_quota_sets_detail(project_id: str, target_project_id: str, request: Request):
    _require_token(request)
    details = {k: {"limit": v, "in_use": 0, "reserved": 0, "allocated": 0} for k, v in _DEFAULT_CINDER_QUOTA.items()}
    return {"quota_set": {**details, "id": target_project_id}}


# ── Volume limits ─────────────────────────────────────────

@router.get("/v3/{project_id}/limits")
async def get_cinder_limits(project_id: str, request: Request):
    _require_token(request)
    return {
        "limits": {
            "absolute": {
                "maxTotalVolumes": 10,
                "maxTotalSnapshots": 10,
                "maxTotalVolumeGigabytes": 1000,
                "maxTotalBackups": 10,
                "maxTotalBackupGigabytes": 1000,
                "totalVolumesUsed": 0,
                "totalGigabytesUsed": 0,
                "totalSnapshotsUsed": 0,
                "totalBackupsUsed": 0,
                "totalBackupGigabytesUsed": 0,
            },
            "rate": [],
        }
    }
