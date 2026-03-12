"""Nova Pydantic v2 models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


# ── Server ────────────────────────────────────────────────

class ServerCreateRequest(BaseModel):
    name: str
    imageRef: str = ""
    flavorRef: str = ""
    key_name: Optional[str] = None
    security_groups: list[dict] | None = None
    networks: list[dict] | None = None
    metadata: dict | None = None


class ServerUpdateRequest(BaseModel):
    name: Optional[str] = None


# ── Flavor ────────────────────────────────────────────────

class FlavorCreateRequest(BaseModel):
    name: str
    vcpus: int = 1
    ram: int = 512
    disk: int = 1
    ephemeral: int = 0
    swap: str | int = ""
    rxtx_factor: float = 1.0
    is_public: bool = True
    id: Optional[str] = None


# ── Keypair ───────────────────────────────────────────────

class KeypairCreateRequest(BaseModel):
    name: str
    public_key: Optional[str] = None
    type: str = "ssh"
    user_id: Optional[str] = None
