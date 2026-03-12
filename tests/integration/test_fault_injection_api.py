"""Integration tests for fault injection admin API."""

import os
import subprocess
import time

import httpx
import pytest

KEYSTONE_PORT = 25200
NOVA_PORT = 28810
NEUTRON_PORT = 29730
GLANCE_PORT = 29330
CINDER_PORT = 28811
PLACEMENT_PORT = 28991
ADMIN_PORT = 29999

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
NOVA_URL = f"http://localhost:{NOVA_PORT}"
ADMIN_URL = f"http://localhost:{ADMIN_PORT}"


@pytest.fixture(scope="module")
def server_process():
    env = os.environ.copy()
    env.update({
        "LOCALOSTACK_KEYSTONE_PORT": str(KEYSTONE_PORT),
        "LOCALOSTACK_NOVA_PORT": str(NOVA_PORT),
        "LOCALOSTACK_NEUTRON_PORT": str(NEUTRON_PORT),
        "LOCALOSTACK_GLANCE_PORT": str(GLANCE_PORT),
        "LOCALOSTACK_CINDER_PORT": str(CINDER_PORT),
        "LOCALOSTACK_PLACEMENT_PORT": str(PLACEMENT_PORT),
        "LOCALOSTACK_ADMIN_PORT": str(ADMIN_PORT),
        "LOCALOSTACK_HOST": "127.0.0.1",
        "LOCALOSTACK_ENDPOINT_HOST": "localhost",
    })
    proc = subprocess.Popen(
        ["uv", "run", "localostack"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/Users/byeonjaehan/projects/localostack",
    )
    for _ in range(30):
        try:
            httpx.get(f"{KEYSTONE_URL}/", timeout=1)
            break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        proc.kill()
        raise RuntimeError("Server failed to start")
    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="module")
def token(server_process):
    r = httpx.post(
        f"{KEYSTONE_URL}/v3/auth/tokens",
        json={"auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": "admin", "password": "password", "domain": {"name": "Default"}}}},
            "scope": {"project": {"name": "admin", "domain": {"name": "Default"}}},
        }},
        timeout=5,
    )
    return r.headers["X-Subject-Token"]


@pytest.fixture(autouse=True)
def clear_rules(server_process):
    """Clear all fault rules before each test."""
    httpx.delete(f"{ADMIN_URL}/admin/fault-rules", timeout=5)
    yield
    httpx.delete(f"{ADMIN_URL}/admin/fault-rules", timeout=5)


class TestAdminAPI:
    def test_health(self, server_process):
        r = httpx.get(f"{ADMIN_URL}/admin/health", timeout=5)
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_list_rules_empty(self, server_process):
        r = httpx.get(f"{ADMIN_URL}/admin/fault-rules", timeout=5)
        assert r.status_code == 200
        assert r.json()["rules"] == []

    def test_add_rule(self, server_process):
        r = httpx.post(
            f"{ADMIN_URL}/admin/fault-rules",
            json={"service": "nova", "action": "error", "status_code": 503},
            timeout=5,
        )
        assert r.status_code == 201
        rule = r.json()
        assert rule["service"] == "nova"
        assert rule["status_code"] == 503
        assert "id" in rule

    def test_delete_rule(self, server_process):
        # Add then delete
        r = httpx.post(f"{ADMIN_URL}/admin/fault-rules",
            json={"action": "error"}, timeout=5)
        rule_id = r.json()["id"]

        r2 = httpx.delete(f"{ADMIN_URL}/admin/fault-rules/{rule_id}", timeout=5)
        assert r2.status_code == 200
        assert r2.json()["deleted"] == rule_id

    def test_delete_nonexistent_rule_returns_404(self, server_process):
        r = httpx.delete(f"{ADMIN_URL}/admin/fault-rules/nonexistent", timeout=5)
        assert r.status_code == 404


class TestFaultInjectionBehavior:
    def test_error_rule_returns_injected_status(self, server_process, token):
        # Add error rule for Nova list servers
        httpx.post(f"{ADMIN_URL}/admin/fault-rules", json={
            "service": "nova", "method": "GET",
            "path_pattern": "/v2.1/servers",
            "action": "error", "status_code": 503,
            "error_message": "Nova is down",
        }, timeout=5)

        # Call Nova list servers — should get 503
        r = httpx.get(f"{NOVA_URL}/v2.1/servers",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 503

    def test_error_rule_removed_restores_normal(self, server_process, token):
        r = httpx.post(f"{ADMIN_URL}/admin/fault-rules", json={
            "service": "nova", "action": "error", "status_code": 500,
        }, timeout=5)
        rule_id = r.json()["id"]

        # Verify it's failing
        r1 = httpx.get(f"{NOVA_URL}/v2.1/servers",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r1.status_code == 500

        # Remove rule
        httpx.delete(f"{ADMIN_URL}/admin/fault-rules/{rule_id}", timeout=5)

        # Now should work
        r2 = httpx.get(f"{NOVA_URL}/v2.1/servers",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r2.status_code == 200

    def test_count_one_rule_applies_once(self, server_process, token):
        httpx.post(f"{ADMIN_URL}/admin/fault-rules", json={
            "service": "nova", "method": "GET",
            "path_pattern": "/v2.1/flavors",
            "action": "error", "status_code": 503,
            "count": 1,
        }, timeout=5)

        r1 = httpx.get(f"{NOVA_URL}/v2.1/flavors",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r1.status_code == 503

        r2 = httpx.get(f"{NOVA_URL}/v2.1/flavors",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r2.status_code == 200

    def test_delay_rule_still_returns_response(self, server_process, token):
        httpx.post(f"{ADMIN_URL}/admin/fault-rules", json={
            "service": "nova", "action": "delay", "delay_ms": 50,
        }, timeout=5)

        r = httpx.get(f"{NOVA_URL}/v2.1/flavors",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200  # still responds, just delayed

    def test_wildcard_service_affects_all(self, server_process, token):
        httpx.post(f"{ADMIN_URL}/admin/fault-rules", json={
            "service": "*", "method": "GET", "path_pattern": "/v2.1/flavors",
            "action": "error", "status_code": 418,
        }, timeout=5)

        r = httpx.get(f"{NOVA_URL}/v2.1/flavors",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 418

    def test_env_var_fault_rules_loaded_at_startup(self):
        """Verify LOCALOSTACK_FAULT_RULES env var loads rules at startup."""
        import json
        rules = [{"service": "nova", "action": "error", "status_code": 503,
                  "path_pattern": "/v2.1/servers"}]

        env = os.environ.copy()
        env.update({
            "LOCALOSTACK_KEYSTONE_PORT": "25210",
            "LOCALOSTACK_NOVA_PORT": "28820",
            "LOCALOSTACK_NEUTRON_PORT": "29740",
            "LOCALOSTACK_GLANCE_PORT": "29340",
            "LOCALOSTACK_CINDER_PORT": "28821",
            "LOCALOSTACK_PLACEMENT_PORT": "28993",
            "LOCALOSTACK_ADMIN_PORT": "29998",
            "LOCALOSTACK_HOST": "127.0.0.1",
            "LOCALOSTACK_ENDPOINT_HOST": "localhost",
            "LOCALOSTACK_FAULT_RULES": json.dumps(rules),
        })
        p = subprocess.Popen(
            ["uv", "run", "localostack"], env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd="/Users/byeonjaehan/projects/localostack",
        )
        try:
            for _ in range(30):
                try:
                    httpx.get("http://localhost:25210/", timeout=1)
                    break
                except httpx.ConnectError:
                    time.sleep(0.5)

            # Check admin API shows the rule
            r = httpx.get("http://localhost:29998/admin/fault-rules", timeout=5)
            assert r.status_code == 200
            rules_list = r.json()["rules"]
            assert len(rules_list) == 1
            assert rules_list[0]["service"] == "nova"
            assert rules_list[0]["status_code"] == 503
        finally:
            p.terminate()
            p.wait(timeout=5)
