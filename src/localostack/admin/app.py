"""LocalOStack Admin API — fault injection management."""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

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


def _build_dashboard_html(services_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LocalOStack Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{ font-family: 'Courier New', monospace; background: #1a1a2e; color: #e0e0e0; padding: 2rem; min-height: 100vh; }}
    h1 {{ color: #00d4ff; font-size: 1.8rem; margin-bottom: 0.25rem; }}
    .subtitle {{ color: #666; margin-bottom: 2.5rem; font-size: 0.9rem; }}
    .section-title {{ color: #00d4ff; margin: 2rem 0 1rem; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.12em; border-bottom: 1px solid #0f3460; padding-bottom: 0.5rem; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }}
    .card {{ background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 1.2rem; transition: border-color 0.2s; }}
    .card:hover {{ border-color: #00d4ff44; }}
    .card h3 {{ margin: 0 0 0.6rem; color: #9ab; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 6px; }}
    .card .service-label {{ font-size: 1rem; font-weight: bold; margin-bottom: 0.3rem; }}
    .card .port {{ color: #555; font-size: 0.78rem; }}
    .status-dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
    .up {{ background: #00ff88; box-shadow: 0 0 6px #00ff8866; }}
    .down {{ background: #ff4444; box-shadow: 0 0 6px #ff444466; }}
    .checking {{ background: #ffaa00; animation: pulse 1s infinite; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.4; }} }}
    .admin-links {{ background: #16213e; border: 1px solid #0f3460; border-radius: 8px; padding: 1.2rem; display: flex; gap: 1.5rem; flex-wrap: wrap; }}
    .admin-links a {{ color: #00d4ff; text-decoration: none; font-size: 0.9rem; }}
    .admin-links a:hover {{ text-decoration: underline; }}
    .actions {{ margin-top: 2rem; display: flex; align-items: center; gap: 1rem; }}
    .refresh-btn {{ background: transparent; color: #00d4ff; border: 1px solid #00d4ff; padding: 0.4rem 1rem; border-radius: 4px; cursor: pointer; font-family: inherit; font-size: 0.85rem; transition: all 0.2s; }}
    .refresh-btn:hover {{ background: #00d4ff; color: #1a1a2e; }}
    .last-check {{ color: #555; font-size: 0.78rem; }}
  </style>
</head>
<body>
  <h1>LocalOStack</h1>
  <div class="subtitle">Local OpenStack API Emulator — Dashboard</div>

  <div class="section-title">Services</div>
  <div class="grid" id="services-grid"></div>

  <div class="section-title">Admin</div>
  <div class="admin-links">
    <a href="/admin/health">Health Status</a>
    <a href="/admin/fault-rules">Fault Rules API</a>
  </div>

  <div class="actions">
    <button class="refresh-btn" onclick="checkAll()">&#x21BA; Refresh</button>
    <span class="last-check" id="last-check"></span>
  </div>

  <script>
    const SERVICES = {services_json};

    function renderServices() {{
      const grid = document.getElementById('services-grid');
      grid.innerHTML = SERVICES.map(s => `
        <div class="card">
          <h3><span class="status-dot checking" id="dot-${{s.name}}"></span>${{s.name}}</h3>
          <div class="service-label" id="label-${{s.name}}" style="color:#ffaa00">checking...</div>
          <div class="port">port ${{s.port}}</div>
        </div>
      `).join('');
    }}

    async function checkService(s) {{
      const dot = document.getElementById(`dot-${{s.name}}`);
      const label = document.getElementById(`label-${{s.name}}`);
      try {{
        await fetch(`http://localhost:${{s.port}}/`, {{signal: AbortSignal.timeout(2000)}});
        dot.className = 'status-dot up';
        label.textContent = 'UP';
        label.style.color = '#00ff88';
      }} catch {{
        dot.className = 'status-dot down';
        label.textContent = 'DOWN';
        label.style.color = '#ff4444';
      }}
    }}

    function checkAll() {{
      SERVICES.forEach(s => {{
        const dot = document.getElementById(`dot-${{s.name}}`);
        const label = document.getElementById(`label-${{s.name}}`);
        if (dot) {{ dot.className = 'status-dot checking'; }}
        if (label) {{ label.textContent = 'checking...'; label.style.color = '#ffaa00'; }}
      }});
      Promise.all(SERVICES.map(s => checkService(s))).then(() => {{
        document.getElementById('last-check').textContent =
          'Last checked: ' + new Date().toLocaleTimeString();
      }});
    }}

    renderServices();
    checkAll();
    setInterval(checkAll, 10000);
  </script>
</body>
</html>"""


def create_admin_app(registry: FaultRegistry, config=None) -> FastAPI:
    app = FastAPI(title="LocalOStack Admin", version="1.0")

    # Build services list from config (or defaults)
    from localostack.core.config import ServiceConfig
    cfg = config if config is not None else ServiceConfig()
    _services = [
        {"name": "keystone", "port": cfg.keystone_port},
        {"name": "nova", "port": cfg.nova_port},
        {"name": "neutron", "port": cfg.neutron_port},
        {"name": "glance", "port": cfg.glance_port},
        {"name": "cinder", "port": cfg.cinder_port},
        {"name": "placement", "port": cfg.placement_port},
        {"name": "heat", "port": cfg.heat_port},
    ]
    _dashboard_html = _build_dashboard_html(json.dumps(_services))

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return HTMLResponse(content=_dashboard_html)

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
