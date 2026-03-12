from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Image:
    id: str
    name: str
    status: str = "queued"  # queued / saving / active / deleted
    visibility: str = "private"  # public / private / shared / community
    container_format: str = "bare"
    disk_format: str = "qcow2"
    min_disk: int = 0
    min_ram: int = 0
    size: Optional[int] = None
    checksum: Optional[str] = None
    owner: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)
    properties: dict = field(default_factory=dict)
    file_data: Optional[bytes] = None


class GlanceStore:
    def __init__(self, backend=None):
        self._b = backend
        self.images: dict[str, Image] = {}

    def _save(self, image: Image) -> None:
        if self._b:
            data = asdict(image)
            # file_data (bytes) is not JSON serializable; skip it
            data.pop("file_data", None)
            self._b.put("glance", "images", image.id, data)

    def _del(self, image_id: str) -> None:
        if self._b:
            self._b.delete("glance", "images", image_id)

    def _load_persisted(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("glance", "images"):
            img = Image(**data)
            self.images[img.id] = img

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # ── CRUD ────────────────────────────────────────────────

    def create_image(
        self,
        *,
        name: str,
        container_format: str = "bare",
        disk_format: str = "qcow2",
        visibility: str = "private",
        min_disk: int = 0,
        min_ram: int = 0,
        tags: list[str] | None = None,
        properties: dict | None = None,
        owner: str = "",
    ) -> Image:
        now = self._now()
        image = Image(
            id=self._uuid(),
            name=name,
            container_format=container_format,
            disk_format=disk_format,
            visibility=visibility,
            min_disk=min_disk,
            min_ram=min_ram,
            tags=tags or [],
            properties=properties or {},
            owner=owner,
            created_at=now,
            updated_at=now,
        )
        self.images[image.id] = image
        self._save(image)
        return image

    def get_image(self, image_id: str) -> Optional[Image]:
        img = self.images.get(image_id)
        if img and img.status == "deleted":
            return None
        return img

    def list_images(self, owner: Optional[str] = None, visibility: Optional[str] = None) -> list[Image]:
        result = []
        for img in self.images.values():
            if img.status == "deleted":
                continue
            if owner and img.visibility != "public" and img.owner != owner:
                continue
            if visibility and img.visibility != visibility:
                continue
            result.append(img)
        return result

    def update_image(self, image_id: str, **kwargs) -> Optional[Image]:
        img = self.get_image(image_id)
        if img is None:
            return None
        for key, value in kwargs.items():
            if hasattr(img, key) and key not in ("id", "created_at"):
                setattr(img, key, value)
        img.updated_at = self._now()
        self._save(img)
        return img

    def delete_image(self, image_id: str) -> bool:
        img = self.get_image(image_id)
        if img is None:
            return False
        img.status = "deleted"
        img.updated_at = self._now()
        self._del(image_id)
        return True

    # ── File operations ─────────────────────────────────────

    def upload_file(self, image_id: str, data: bytes) -> Optional[Image]:
        img = self.get_image(image_id)
        if img is None:
            return None
        img.file_data = data
        img.size = len(data)
        img.checksum = hashlib.md5(data).hexdigest()
        img.status = "active"
        img.updated_at = self._now()
        self._save(img)
        return img

    def download_file(self, image_id: str) -> Optional[bytes]:
        img = self.get_image(image_id)
        if img is None:
            return None
        return img.file_data

    # ── Tags ────────────────────────────────────────────────

    def add_tag(self, image_id: str, tag: str) -> Optional[Image]:
        img = self.get_image(image_id)
        if img is None:
            return None
        if tag not in img.tags:
            img.tags.append(tag)
            img.updated_at = self._now()
            self._save(img)
        return img

    def delete_tag(self, image_id: str, tag: str) -> bool:
        img = self.get_image(image_id)
        if img is None:
            return False
        if tag not in img.tags:
            return False
        img.tags.remove(tag)
        img.updated_at = self._now()
        self._save(img)
        return True

    # ── Bootstrap ───────────────────────────────────────────

    def bootstrap(self, *, admin_project_id: str):
        self._load_persisted()
        if not self.images:
            now = self._now()
            cirros = Image(
                id=self._uuid(),
                name="cirros-0.6.2",
                status="active",
                visibility="public",
                container_format="bare",
                disk_format="qcow2",
                min_disk=0,
                min_ram=0,
                size=0,
                owner=admin_project_id,
                created_at=now,
                updated_at=now,
            )
            self.images[cirros.id] = cirros
            self._save(cirros)
