"""Cinder in-memory store."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Volume:
    id: str
    name: str
    size: int = 1
    status: str = "available"
    volume_type: str = ""
    availability_zone: str = "nova"
    bootable: bool = False
    encrypted: bool = False
    description: str = ""
    metadata: dict = field(default_factory=dict)
    attachments: list[dict] = field(default_factory=list)
    tenant_id: str = ""
    user_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    snapshot_id: Optional[str] = None
    source_volid: Optional[str] = None


@dataclass
class VolumeType:
    id: str
    name: str
    description: str = ""
    is_public: bool = True
    extra_specs: dict = field(default_factory=dict)


@dataclass
class Snapshot:
    id: str
    name: str
    volume_id: str
    size: int = 1
    status: str = "available"
    description: str = ""
    metadata: dict = field(default_factory=dict)
    tenant_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class CinderStore:
    def __init__(self, backend=None):
        self._b = backend
        self.volumes: dict[str, Volume] = {}
        self.volume_types: dict[str, VolumeType] = {}
        self.snapshots: dict[str, Snapshot] = {}

    def _save(self, rtype: str, id: str, obj) -> None:
        if self._b:
            self._b.put("cinder", rtype, id, asdict(obj))

    def _del(self, rtype: str, id: str) -> None:
        if self._b:
            self._b.delete("cinder", rtype, id)

    def _load_persisted(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("cinder", "volumes"):
            vol = Volume(**data)
            self.volumes[vol.id] = vol
        for data in self._b.get_all("cinder", "snapshots"):
            snap = Snapshot(**data)
            self.snapshots[snap.id] = snap
        for data in self._b.get_all("cinder", "volume_types"):
            vt = VolumeType(**data)
            self.volume_types[vt.id] = vt

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _now() -> str:
        # gophercloud Cinder uses RFC3339MilliNoZ: no Z suffix, 3-digit milliseconds
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}"

    # ── Volume CRUD ───────────────────────────────────────

    def create_volume(
        self,
        *,
        name: str,
        size: int = 1,
        volume_type: str = "",
        availability_zone: str = "nova",
        description: str = "",
        metadata: Optional[dict] = None,
        snapshot_id: Optional[str] = None,
        source_volid: Optional[str] = None,
        tenant_id: str = "",
        user_id: str = "",
    ) -> Volume:
        now = self._now()
        vol = Volume(
            id=self._uuid(),
            name=name,
            size=size,
            volume_type=volume_type,
            availability_zone=availability_zone,
            description=description,
            metadata=metadata or {},
            snapshot_id=snapshot_id,
            source_volid=source_volid,
            tenant_id=tenant_id,
            user_id=user_id,
            created_at=now,
            updated_at=now,
        )
        self.volumes[vol.id] = vol
        self._save("volumes", vol.id, vol)
        return vol

    def get_volume(self, volume_id: str) -> Optional[Volume]:
        return self.volumes.get(volume_id)

    def list_volumes(self) -> list[Volume]:
        return [v for v in self.volumes.values() if v.status != "deleting"]

    def update_volume(self, volume_id: str, **kwargs) -> Optional[Volume]:
        vol = self.get_volume(volume_id)
        if vol is None:
            return None
        for key, value in kwargs.items():
            if hasattr(vol, key) and key not in ("id", "created_at"):
                setattr(vol, key, value)
        vol.updated_at = self._now()
        self._save("volumes", vol.id, vol)
        return vol

    def delete_volume(self, volume_id: str) -> bool:
        vol = self.volumes.get(volume_id)
        if vol is None:
            return False
        del self.volumes[volume_id]
        self._del("volumes", volume_id)
        return True

    # ── Snapshot CRUD ─────────────────────────────────────

    def create_snapshot(
        self,
        *,
        name: str,
        volume_id: str,
        description: str = "",
        metadata: Optional[dict] = None,
        tenant_id: str = "",
    ) -> Snapshot:
        now = self._now()
        vol = self.get_volume(volume_id)
        size = vol.size if vol else 1
        snap = Snapshot(
            id=self._uuid(),
            name=name,
            volume_id=volume_id,
            size=size,
            description=description,
            metadata=metadata or {},
            tenant_id=tenant_id,
            created_at=now,
            updated_at=now,
        )
        self.snapshots[snap.id] = snap
        self._save("snapshots", snap.id, snap)
        return snap

    def get_snapshot(self, snapshot_id: str) -> Optional[Snapshot]:
        return self.snapshots.get(snapshot_id)

    def list_snapshots(self) -> list[Snapshot]:
        return list(self.snapshots.values())

    def delete_snapshot(self, snapshot_id: str) -> bool:
        if snapshot_id not in self.snapshots:
            return False
        del self.snapshots[snapshot_id]
        self._del("snapshots", snapshot_id)
        return True

    # ── VolumeType ────────────────────────────────────────

    def get_volume_type(self, type_id: str) -> Optional[VolumeType]:
        return self.volume_types.get(type_id)

    def list_volume_types(self) -> list[VolumeType]:
        return list(self.volume_types.values())

    # ── Bootstrap ─────────────────────────────────────────

    def bootstrap(self):
        self._load_persisted()
        if not self.volume_types:
            vt = VolumeType(id="1", name="__DEFAULT__")
            self.volume_types[vt.id] = vt
            self._save("volume_types", vt.id, vt)
