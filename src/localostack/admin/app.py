"""LocalOStack Admin API — fault injection management."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from localostack.core.fault_injection import FaultRegistry, FaultRule


def _rule_to_dict(rule: FaultRule) -> dict:
    return {
        "id": rule.id,
        "service": rule.service,
        "method": rule.method,
        "path_pattern": rule.path_pattern,
        "action": rule.action,
        "status_code": rule.status_code,
        "error_message": rule.error_message,
        "delay_ms": rule.delay_ms,
        "throttle_max": rule.throttle_max,
        "throttle_window_sec": rule.throttle_window_sec,
        "count": rule.count,
        "probability": rule.probability,
        "hit_count": rule._hit_count,
    }


def create_admin_app(registry: FaultRegistry) -> FastAPI:
    app = FastAPI(title="LocalOStack Admin", version="1.0")

    @app.get("/admin/health")
    async def health():
        return {"status": "ok", "rules": len(registry.get_rules())}

    @app.get("/admin/fault-rules")
    async def list_rules():
        return {"rules": [_rule_to_dict(r) for r in registry.get_rules()]}

    @app.post("/admin/fault-rules", status_code=201)
    async def add_rule(body: dict):
        # strip internal fields
        data = {k: v for k, v in body.items() if not k.startswith("_")}
        rule = FaultRule(**data)
        registry.add_rule(rule)
        return _rule_to_dict(rule)

    @app.get("/admin/fault-rules/{rule_id}")
    async def get_rule(rule_id: str):
        rule = registry.get_rule(rule_id)
        if rule is None:
            return JSONResponse(status_code=404, content={"error": "Rule not found"})
        return _rule_to_dict(rule)

    @app.delete("/admin/fault-rules/{rule_id}")
    async def delete_rule(rule_id: str):
        if not registry.remove_rule(rule_id):
            return JSONResponse(status_code=404, content={"error": "Rule not found"})
        return {"deleted": rule_id}

    @app.delete("/admin/fault-rules")
    async def clear_rules():
        count = len(registry.get_rules())
        registry.clear()
        return {"cleared": count}

    return app
