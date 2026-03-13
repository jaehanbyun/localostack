"""Barbican Key Manager API integration tests."""

import os
import pathlib
import subprocess
import time

import httpx
import pytest

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent.parent)

KEYSTONE_PORT = 25600
NOVA_PORT = 28860
NEUTRON_PORT = 29780
GLANCE_PORT = 29380
CINDER_PORT = 28861
PLACEMENT_PORT = 28862
HEAT_PORT = 28863
SWIFT_PORT = 28864
BARBICAN_PORT = 29312
OCTAVIA_PORT = 29883
ADMIN_PORT = 29907

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
BARBICAN_URL = f"http://localhost:{BARBICAN_PORT}"


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
        "LOCALOSTACK_HEAT_PORT": str(HEAT_PORT),
        "LOCALOSTACK_SWIFT_PORT": str(SWIFT_PORT),
        "LOCALOSTACK_BARBICAN_PORT": str(BARBICAN_PORT),
        "LOCALOSTACK_OCTAVIA_PORT": str(OCTAVIA_PORT),
        "LOCALOSTACK_ADMIN_PORT": str(ADMIN_PORT),
        "LOCALOSTACK_HOST": "127.0.0.1",
        "LOCALOSTACK_ENDPOINT_HOST": "localhost",
    })
    proc = subprocess.Popen(
        ["uv", "run", "localostack"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=_PROJECT_ROOT,
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
    r = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json={
        "auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": "admin", "password": "password", "domain": {"name": "Default"}}}},
            "scope": {"project": {"name": "admin", "domain": {"name": "Default"}}},
        }}, timeout=5)
    return r.headers["X-Subject-Token"]


class TestBarbicanAPI:
    def test_version_discovery(self, server_process):
        r = httpx.get(f"{BARBICAN_URL}/", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert "versions" in data
        values = data["versions"]["values"]
        assert len(values) >= 1
        assert values[0]["id"] == "v1"

    def test_list_secrets_empty(self, server_process, token):
        r = httpx.get(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["secrets"] == []
        assert data["total"] == 0

    def test_create_secret(self, server_process, token):
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={"name": "my-secret", "secret_type": "opaque"},
            timeout=5,
        )
        assert r.status_code == 201
        data = r.json()
        assert "secret_ref" in data
        assert "/v1/secrets/" in data["secret_ref"]

    def test_create_secret_with_payload(self, server_process, token):
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={
                "name": "payload-secret",
                "payload": "supersecretvalue",
                "payload_content_type": "text/plain",
                "secret_type": "opaque",
            },
            timeout=5,
        )
        assert r.status_code == 201
        data = r.json()
        assert "secret_ref" in data
        # Extract id and check detail
        secret_id = data["secret_ref"].split("/")[-1]
        r2 = httpx.get(
            f"{BARBICAN_URL}/v1/secrets/{secret_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        detail = r2.json()
        assert detail["status"] == "ACTIVE"
        assert detail["name"] == "payload-secret"

    def test_get_secret(self, server_process, token):
        # Create a secret first
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={"name": "get-test-secret", "payload": "somevalue"},
            timeout=5,
        )
        assert r.status_code == 201
        secret_id = r.json()["secret_ref"].split("/")[-1]

        r2 = httpx.get(
            f"{BARBICAN_URL}/v1/secrets/{secret_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        detail = r2.json()
        assert detail["name"] == "get-test-secret"
        assert "secret_ref" in detail
        assert "status" in detail
        assert "created" in detail
        assert "updated" in detail

    def test_get_payload(self, server_process, token):
        # Create a secret with payload
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={
                "name": "payload-fetch-secret",
                "payload": "hello-payload",
                "payload_content_type": "text/plain",
            },
            timeout=5,
        )
        assert r.status_code == 201
        secret_id = r.json()["secret_ref"].split("/")[-1]

        r2 = httpx.get(
            f"{BARBICAN_URL}/v1/secrets/{secret_id}/payload",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        assert r2.text == "hello-payload"

    def test_list_secrets(self, server_process, token):
        # Create a known secret
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={"name": "list-test-secret"},
            timeout=5,
        )
        assert r.status_code == 201
        secret_ref = r.json()["secret_ref"]

        r2 = httpx.get(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["total"] >= 1
        refs = [s["secret_ref"] for s in data["secrets"]]
        assert secret_ref in refs

    def test_delete_secret(self, server_process, token):
        # Create a secret
        r = httpx.post(
            f"{BARBICAN_URL}/v1/secrets",
            headers={"X-Auth-Token": token},
            json={"name": "delete-test-secret"},
            timeout=5,
        )
        assert r.status_code == 201
        secret_id = r.json()["secret_ref"].split("/")[-1]

        # Delete it
        r2 = httpx.delete(
            f"{BARBICAN_URL}/v1/secrets/{secret_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 204

        # Subsequent GET returns 404
        r3 = httpx.get(
            f"{BARBICAN_URL}/v1/secrets/{secret_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r3.status_code == 404
