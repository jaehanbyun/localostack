from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ImageCreateRequest(BaseModel):
    name: str
    container_format: str = "bare"
    disk_format: str = "qcow2"
    visibility: str = "private"
    min_disk: int = 0
    min_ram: int = 0
    tags: list[str] = []
    properties: dict[str, Any] = {}


class ImageUpdateRequest(BaseModel):
    name: Optional[str] = None
    container_format: Optional[str] = None
    disk_format: Optional[str] = None
    visibility: Optional[str] = None
    min_disk: Optional[int] = None
    min_ram: Optional[int] = None
    tags: Optional[list[str]] = None


class ImageResponse(BaseModel):
    id: str
    name: str
    status: str
    visibility: str
    container_format: str
    disk_format: str
    min_disk: int
    min_ram: int
    size: Optional[int] = None
    checksum: Optional[str] = None
    owner: str
    created_at: str
    updated_at: str
    tags: list[str]
    self_: str
    file: str
    schema_: str

    class Config:
        populate_by_name = True
