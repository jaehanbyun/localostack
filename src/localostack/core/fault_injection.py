"""Fault injection — rule registry and request middleware."""

from __future__ import annotations

import asyncio
import fnmatch
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse


@dataclass
class FaultRule:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    service: str = "*"        # nova | neutron | glance | cinder | keystone | *
    method: str = "*"         # GET | POST | PUT | DELETE | PATCH | *
    path_pattern: str = "*"   # glob or "regex:..." pattern
    action: str = "error"     # error | delay | timeout | throttle

    # error action
    status_code: int = 500
    error_message: str = "Injected fault"

    # delay action (milliseconds)
    delay_ms: int = 1000

    # throttle action
    throttle_max: int = 5         # allow N calls per window
    throttle_window_sec: int = 60

    # common
    count: int = 0            # 0=infinite, N=apply N times then stop
    probability: float = 1.0  # 0.0-1.0

    # runtime state (not serialized)
    _hit_count: int = field(default=0, repr=False, compare=False)
    _throttle_hits: list = field(default_factory=list, repr=False, compare=False)


class FaultRegistry:
    """Thread-safe (within single asyncio loop) registry of fault rules."""

    def __init__(self) -> None:
        self._rules: dict[str, FaultRule] = {}

    def add_rule(self, rule: FaultRule) -> FaultRule:
        self._rules[rule.id] = rule
        return rule

    def get_rules(self) -> list[FaultRule]:
        return list(self._rules.values())

    def get_rule(self, rule_id: str) -> Optional[FaultRule]:
        return self._rules.get(rule_id)

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id not in self._rules:
            return False
        del self._rules[rule_id]
        return True

    def clear(self) -> None:
        self._rules.clear()

    def match(self, service: str, method: str, path: str) -> Optional[FaultRule]:
        for rule in self._rules.values():
            # service match
            if rule.service != "*" and rule.service != service:
                continue
            # method match
            if rule.method != "*" and rule.method.upper() != method.upper():
                continue
            # path pattern match
            if not _match_path(rule.path_pattern, path):
                continue
            # count exhausted?
            if rule.count > 0 and rule._hit_count >= rule.count:
                continue
            # probability
            if rule.probability < 1.0:
                import random
                if random.random() > rule.probability:
                    continue
            return rule
        return None


def _match_path(pattern: str, path: str) -> bool:
    if pattern.startswith("regex:"):
        return bool(re.fullmatch(pattern[6:], path))
    return fnmatch.fnmatch(path, pattern)


def make_fault_middleware(registry: FaultRegistry, service_name: str):
    """Return an ASGI middleware coroutine for the given service."""

    async def fault_middleware(request: Request, call_next):
        rule = registry.match(service_name, request.method, request.url.path)
        if rule is None:
            return await call_next(request)

        rule._hit_count += 1

        if rule.action == "error":
            return JSONResponse(
                status_code=rule.status_code,
                content={"error": {"message": rule.error_message, "code": rule.status_code}},
            )

        elif rule.action == "delay":
            await asyncio.sleep(rule.delay_ms / 1000.0)
            return await call_next(request)

        elif rule.action == "timeout":
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                raise
            return Response(status_code=504, content=b"Gateway Timeout")

        elif rule.action == "throttle":
            now = time.monotonic()
            rule._throttle_hits = [
                t for t in rule._throttle_hits
                if now - t < rule.throttle_window_sec
            ]
            if len(rule._throttle_hits) >= rule.throttle_max:
                return JSONResponse(
                    status_code=429,
                    content={"error": {"message": "Too Many Requests", "code": 429}},
                    headers={"Retry-After": str(rule.throttle_window_sec)},
                )
            rule._throttle_hits.append(now)
            return await call_next(request)

        return await call_next(request)

    return fault_middleware
