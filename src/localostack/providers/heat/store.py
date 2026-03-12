"""Heat (Orchestration) in-memory store."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Stack:
    id: str
    name: str
    tenant_id: str = "admin"
    status: str = "CREATE_COMPLETE"
    status_reason: str = "Stack CREATE completed successfully"
    template: dict = field(default_factory=dict)
    parameters: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    resources: list = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    tags: list = field(default_factory=list)


class HeatStore:
    def __init__(self, backend=None):
        self._b = backend
        self._stacks: dict[str, Stack] = {}
        self._events: dict[str, list[dict]] = {}
        self._load_persisted()

    def _save(self, stack: Stack) -> None:
        if self._b:
            self._b.put("heat", "stack", stack.id, asdict(stack))

    def _del(self, stack_id: str) -> None:
        if self._b:
            self._b.delete("heat", "stack", stack_id)

    def _load_persisted(self) -> None:
        if not self._b:
            return
        for data in self._b.get_all("heat", "stack"):
            s = Stack(**data)
            self._stacks[s.id] = s

    @staticmethod
    def _uuid() -> str:
        return str(uuid.uuid4())

    def _parse_resources(self, template: dict) -> list[dict]:
        resources = []
        for name, props in template.get("resources", {}).items():
            if not isinstance(props, dict):
                continue
            resources.append({
                "resource_name": name,
                "resource_type": props.get("type", "Unknown"),
                "resource_status": "CREATE_COMPLETE",
                "physical_resource_id": self._uuid(),
                "logical_resource_id": name,
            })
        return resources

    def create_stack(self, *, name: str, template: dict, parameters: Optional[dict] = None,
                     tags: Optional[list] = None, tenant_id: str = "admin") -> Stack:
        stack_id = self._uuid()
        now = _now()
        resources = self._parse_resources(template)
        stack = Stack(
            id=stack_id,
            name=name,
            tenant_id=tenant_id,
            status="CREATE_COMPLETE",
            status_reason="Stack CREATE completed successfully",
            template=template,
            parameters=parameters or {},
            outputs={},
            resources=resources,
            created_at=now,
            updated_at=now,
            tags=tags or [],
        )
        self._stacks[stack_id] = stack
        self._save(stack)
        # Record CREATE event
        self._events[stack_id] = [
            {
                "id": self._uuid(),
                "event_time": now,
                "resource_name": name,
                "resource_status": "CREATE_COMPLETE",
                "resource_status_reason": "Stack CREATE completed successfully",
            }
        ]
        return stack

    def get_stack(self, stack_id_or_name: str) -> Optional[Stack]:
        # Lookup by id first
        stack = self._stacks.get(stack_id_or_name)
        if stack:
            return stack
        # Lookup by name
        for s in self._stacks.values():
            if s.name == stack_id_or_name:
                return s
        return None

    def list_stacks(self, tenant_id: Optional[str] = None) -> list[Stack]:
        result = []
        for s in self._stacks.values():
            if tenant_id and s.tenant_id != tenant_id:
                continue
            result.append(s)
        return result

    def update_stack(self, stack_id: str, *, template: Optional[dict] = None,
                     parameters: Optional[dict] = None) -> Optional[Stack]:
        stack = self._stacks.get(stack_id)
        if stack is None:
            return None
        if template is not None:
            stack.template = template
            stack.resources = self._parse_resources(template)
        if parameters is not None:
            stack.parameters = parameters
        stack.updated_at = _now()
        stack.status = "UPDATE_COMPLETE"
        stack.status_reason = "Stack UPDATE completed successfully"
        self._save(stack)
        # Record UPDATE event
        events = self._events.setdefault(stack_id, [])
        events.append({
            "id": self._uuid(),
            "event_time": stack.updated_at,
            "resource_name": stack.name,
            "resource_status": "UPDATE_COMPLETE",
            "resource_status_reason": "Stack UPDATE completed successfully",
        })
        return stack

    def delete_stack(self, stack_id: str) -> bool:
        stack = self._stacks.get(stack_id)
        if stack is None:
            return False
        stack.status = "DELETE_COMPLETE"
        stack.status_reason = "Stack DELETE completed successfully"
        stack.updated_at = _now()
        self._save(stack)
        events = self._events.setdefault(stack_id, [])
        events.append({
            "id": self._uuid(),
            "event_time": stack.updated_at,
            "resource_name": stack.name,
            "resource_status": "DELETE_COMPLETE",
            "resource_status_reason": "Stack DELETE completed successfully",
        })
        return True

    def list_resources(self, stack_id: str) -> list[dict]:
        stack = self._stacks.get(stack_id)
        if stack is None:
            return []
        return list(stack.resources)

    def list_events(self, stack_id: str) -> list[dict]:
        return list(self._events.get(stack_id, []))
