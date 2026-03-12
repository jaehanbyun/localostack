"""Placement in-memory store."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


RESOURCE_CLASSES = ["VCPU", "MEMORY_MB", "DISK_GB", "NETWORK_BANDWIDTH_EGRESS_KILOBITS_PER_SECOND"]


@dataclass
class ResourceProvider:
    uuid: str
    name: str
    generation: int = 0
    parent_provider_uuid: Optional[str] = None


@dataclass
class Inventory:
    resource_provider_uuid: str
    resource_class: str
    total: int = 0
    reserved: int = 0
    min_unit: int = 1
    max_unit: int = 1
    step_size: int = 1
    allocation_ratio: float = 16.0  # overcommit ratio


@dataclass
class Allocation:
    resource_provider_uuid: str
    resource_class: str
    consumer_uuid: str
    project_id: str = ""
    user_id: str = ""
    used: int = 0


class PlacementStore:
    def __init__(self, backend=None):
        self._b = backend
        self.providers: dict[str, ResourceProvider] = {}
        self.inventories: dict[str, dict[str, Inventory]] = {}  # provider_uuid -> {rc -> Inventory}
        self.allocations: dict[str, dict[str, Allocation]] = {}  # consumer_uuid -> {rc -> Allocation}

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    # ── ResourceProvider ─────────────────────────────────

    def create_provider(self, *, name: str, uuid: Optional[str] = None,
                        parent_provider_uuid: Optional[str] = None) -> ResourceProvider:
        rp_uuid = uuid or self._uuid()
        rp = ResourceProvider(uuid=rp_uuid, name=name,
                              parent_provider_uuid=parent_provider_uuid)
        self.providers[rp_uuid] = rp
        self.inventories[rp_uuid] = {}
        return rp

    def get_provider(self, rp_uuid: str) -> Optional[ResourceProvider]:
        return self.providers.get(rp_uuid)

    def list_providers(self) -> list[ResourceProvider]:
        return list(self.providers.values())

    def delete_provider(self, rp_uuid: str) -> bool:
        if rp_uuid not in self.providers:
            return False
        del self.providers[rp_uuid]
        self.inventories.pop(rp_uuid, None)
        return True

    # ── Inventory ────────────────────────────────────────

    def set_inventories(self, rp_uuid: str, inventories: dict[str, dict]) -> Optional[dict[str, Inventory]]:
        """Replace all inventories for a resource provider."""
        if rp_uuid not in self.providers:
            return None
        result = {}
        for rc, data in inventories.items():
            inv = Inventory(
                resource_provider_uuid=rp_uuid,
                resource_class=rc,
                total=data.get("total", 0),
                reserved=data.get("reserved", 0),
                min_unit=data.get("min_unit", 1),
                max_unit=data.get("max_unit", data.get("total", 1)),
                step_size=data.get("step_size", 1),
                allocation_ratio=data.get("allocation_ratio", 16.0),
            )
            result[rc] = inv
        self.inventories[rp_uuid] = result
        self.providers[rp_uuid].generation += 1
        return result

    def get_inventories(self, rp_uuid: str) -> Optional[dict[str, Inventory]]:
        if rp_uuid not in self.providers:
            return None
        return self.inventories.get(rp_uuid, {})

    # ── Allocations ──────────────────────────────────────

    def set_allocations(self, consumer_uuid: str, allocations: list[dict],
                        project_id: str = "", user_id: str = "") -> None:
        """Set (replace) all allocations for a consumer."""
        self.allocations[consumer_uuid] = {}
        for alloc in allocations:
            rp_uuid = alloc["resource_provider"]["uuid"]
            for rc, amount in alloc.get("resources", {}).items():
                a = Allocation(
                    resource_provider_uuid=rp_uuid,
                    resource_class=rc,
                    consumer_uuid=consumer_uuid,
                    project_id=project_id,
                    user_id=user_id,
                    used=amount,
                )
                key = f"{rp_uuid}:{rc}"
                self.allocations[consumer_uuid][key] = a

    def get_allocations_for_consumer(self, consumer_uuid: str) -> dict[str, Allocation]:
        return self.allocations.get(consumer_uuid, {})

    def delete_allocations(self, consumer_uuid: str) -> bool:
        if consumer_uuid not in self.allocations:
            return False
        del self.allocations[consumer_uuid]
        return True

    def get_provider_allocations(self, rp_uuid: str) -> list[Allocation]:
        """Get all allocations against a specific provider."""
        result = []
        for consumer_allocs in self.allocations.values():
            for alloc in consumer_allocs.values():
                if alloc.resource_provider_uuid == rp_uuid:
                    result.append(alloc)
        return result

    def get_usages(self, project_id: Optional[str] = None) -> dict[str, int]:
        """Return {resource_class: total_used} across all providers."""
        usage: dict[str, int] = {}
        for consumer_allocs in self.allocations.values():
            for alloc in consumer_allocs.values():
                if project_id and alloc.project_id != project_id:
                    continue
                usage[alloc.resource_class] = usage.get(alloc.resource_class, 0) + alloc.used
        return usage

    def bootstrap(self) -> ResourceProvider:
        """Create the single default resource provider with large inventory."""
        rp = self.create_provider(name="localostack", uuid="00000000-0000-0000-0000-000000000001")
        self.set_inventories(rp.uuid, {
            "VCPU": {"total": 10000, "allocation_ratio": 16.0},
            "MEMORY_MB": {"total": 10000000, "allocation_ratio": 1.5},
            "DISK_GB": {"total": 100000, "allocation_ratio": 1.0},
        })
        return rp
