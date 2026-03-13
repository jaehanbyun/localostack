"""Barbican Key Manager store."""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Secret:
    id: str
    name: str
    payload: str = ""
    payload_content_type: str = "text/plain"
    algorithm: str = ""
    bit_length: int = 0
    mode: str = ""
    status: str = "ACTIVE"
    created: str = field(default_factory=_now)
    updated: str = field(default_factory=_now)
    secret_type: str = "opaque"
    expiration: Optional[str] = None


class BarbicanStore:
    def __init__(self, backend=None):
        self._b = backend
        self.secrets: dict[str, Secret] = {}

    def _save(self, s: Secret) -> None:
        if self._b:
            self._b.put("barbican", "secrets", s.id, asdict(s))

    def _del(self, secret_id: str) -> None:
        if self._b:
            self._b.delete("barbican", "secrets", secret_id)

    def bootstrap(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("barbican", "secrets"):
            s = Secret(**data)
            self.secrets[s.id] = s

    def create_secret(
        self,
        *,
        name: str = "",
        payload: str = "",
        payload_content_type: str = "text/plain",
        algorithm: str = "",
        bit_length: int = 0,
        mode: str = "",
        secret_type: str = "opaque",
        expiration: Optional[str] = None,
    ) -> Secret:
        s = Secret(
            id=str(uuid.uuid4()),
            name=name,
            payload=payload,
            payload_content_type=payload_content_type,
            algorithm=algorithm,
            bit_length=bit_length,
            mode=mode,
            secret_type=secret_type,
            expiration=expiration,
        )
        self.secrets[s.id] = s
        self._save(s)
        return s

    def get_secret(self, secret_id: str) -> Optional[Secret]:
        return self.secrets.get(secret_id)

    def list_secrets(self) -> list[Secret]:
        return list(self.secrets.values())

    def delete_secret(self, secret_id: str) -> bool:
        if secret_id not in self.secrets:
            return False
        del self.secrets[secret_id]
        self._del(secret_id)
        return True
