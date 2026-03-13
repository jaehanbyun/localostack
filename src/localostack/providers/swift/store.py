"""Swift Object Storage store."""
from __future__ import annotations
import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class SwiftContainer:
    name: str
    account: str
    created_at: str
    metadata: dict = field(default_factory=dict)


@dataclass
class SwiftObject:
    name: str
    container_name: str
    account: str
    content_type: str
    size: int
    etag: str
    created_at: str
    last_modified: str
    content: Optional[bytes] = None  # in-memory only, NOT persisted to backend


class SwiftStore:
    def __init__(self, backend=None):
        self._b = backend
        self.containers: dict[str, SwiftContainer] = {}
        self.objects: dict[str, SwiftObject] = {}

    def _ckey(self, account: str, container: str) -> str:
        return f"{account}/{container}"

    def _okey(self, account: str, container: str, name: str) -> str:
        return f"{account}/{container}/{name}"

    def _save_container(self, c: SwiftContainer) -> None:
        if self._b:
            self._b.put("swift", "containers", self._ckey(c.account, c.name), asdict(c))

    def _del_container(self, account: str, name: str) -> None:
        if self._b:
            self._b.delete("swift", "containers", self._ckey(account, name))

    def _save_object(self, o: SwiftObject) -> None:
        if self._b:
            data = asdict(o)
            data.pop("content", None)  # bytes cannot be JSON-serialized
            self._b.put("swift", "objects", self._okey(o.account, o.container_name, o.name), data)

    def _del_object(self, account: str, container: str, name: str) -> None:
        if self._b:
            self._b.delete("swift", "objects", self._okey(account, container, name))

    def bootstrap(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("swift", "containers"):
            c = SwiftContainer(**data)
            self.containers[self._ckey(c.account, c.name)] = c
        for data in self._b.get_all("swift", "objects"):
            o = SwiftObject(**data)
            self.objects[self._okey(o.account, o.container_name, o.name)] = o

    # ── Container ──

    def create_container(self, account: str, name: str) -> tuple[SwiftContainer, bool]:
        key = self._ckey(account, name)
        if key in self.containers:
            return self.containers[key], False
        c = SwiftContainer(name=name, account=account, created_at=_now())
        self.containers[key] = c
        self._save_container(c)
        return c, True

    def get_container(self, account: str, name: str) -> Optional[SwiftContainer]:
        return self.containers.get(self._ckey(account, name))

    def delete_container(self, account: str, name: str) -> str:
        key = self._ckey(account, name)
        if key not in self.containers:
            return "not_found"
        prefix = f"{account}/{name}/"
        if any(k.startswith(prefix) for k in self.objects):
            return "not_empty"
        del self.containers[key]
        self._del_container(account, name)
        return "deleted"

    def list_containers(self, account: str) -> list[SwiftContainer]:
        prefix = f"{account}/"
        return [c for k, c in self.containers.items() if k.startswith(prefix)]

    # ── Object ──

    def put_object(
        self, account: str, container: str, name: str,
        content: bytes, content_type: str = "application/octet-stream",
    ) -> SwiftObject:
        now = _now()
        o = SwiftObject(
            name=name, container_name=container, account=account,
            content_type=content_type, size=len(content),
            etag=hashlib.md5(content).hexdigest(),
            created_at=now, last_modified=now, content=content,
        )
        self.objects[self._okey(account, container, name)] = o
        self._save_object(o)
        return o

    def get_object(self, account: str, container: str, name: str) -> Optional[SwiftObject]:
        return self.objects.get(self._okey(account, container, name))

    def delete_object(self, account: str, container: str, name: str) -> bool:
        key = self._okey(account, container, name)
        if key not in self.objects:
            return False
        del self.objects[key]
        self._del_object(account, container, name)
        return True

    def list_objects(self, account: str, container: str) -> list[SwiftObject]:
        prefix = f"{account}/{container}/"
        return [o for k, o in self.objects.items() if k.startswith(prefix)]

    # ── Account summary ──

    def account_info(self, account: str) -> dict:
        containers = self.list_containers(account)
        total_objects = sum(len(self.list_objects(account, c.name)) for c in containers)
        total_bytes = sum(o.size for c in containers for o in self.list_objects(account, c.name))
        return {
            "container_count": len(containers),
            "object_count": total_objects,
            "bytes_used": total_bytes,
        }
