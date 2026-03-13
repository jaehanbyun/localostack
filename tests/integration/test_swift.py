"""Swift Object Storage API integration tests."""

import os
import pathlib
import subprocess
import time

import httpx
import pytest

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent.parent)

KEYSTONE_PORT = 25500
NOVA_PORT = 28850
NEUTRON_PORT = 29770
GLANCE_PORT = 29370
CINDER_PORT = 28851
PLACEMENT_PORT = 28852
HEAT_PORT = 28853
SWIFT_PORT = 29903
BARBICAN_PORT = 29317
OCTAVIA_PORT = 29882
ADMIN_PORT = 29904

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
SWIFT_URL = f"http://localhost:{SWIFT_PORT}"


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


@pytest.fixture(scope="module")
def account_id(token):
    r = httpx.get(f"{KEYSTONE_URL}/v3/auth/projects",
        headers={"X-Auth-Token": token}, timeout=5)
    projects = r.json().get("projects", [])
    if projects:
        return projects[0]["id"]
    return "admin"


class TestSwiftAPI:
    def test_account_info(self, server_process, token, account_id):
        r = httpx.get(f"{SWIFT_URL}/v1/{account_id}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        assert "X-Account-Container-Count" in r.headers

    def test_create_container(self, server_process, token, account_id):
        r = httpx.put(f"{SWIFT_URL}/v1/{account_id}/mycontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 201

    def test_create_container_twice_returns_202(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/mycontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        r = httpx.put(f"{SWIFT_URL}/v1/{account_id}/mycontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 202

    def test_list_containers(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/listcontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        r = httpx.get(f"{SWIFT_URL}/v1/{account_id}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert "listcontainer" in names

    def test_upload_and_download_object(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/testcontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        data = b"hello swift object storage"
        r = httpx.put(
            f"{SWIFT_URL}/v1/{account_id}/testcontainer/myobject",
            headers={"X-Auth-Token": token, "Content-Type": "text/plain"},
            content=data,
            timeout=5,
        )
        assert r.status_code == 201
        r2 = httpx.get(
            f"{SWIFT_URL}/v1/{account_id}/testcontainer/myobject",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        assert r2.content == data

    def test_head_object(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/headcontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        data = b"head test data"
        httpx.put(
            f"{SWIFT_URL}/v1/{account_id}/headcontainer/headobj",
            headers={"X-Auth-Token": token, "Content-Type": "application/octet-stream"},
            content=data,
            timeout=5,
        )
        r = httpx.head(
            f"{SWIFT_URL}/v1/{account_id}/headcontainer/headobj",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 200
        assert "Content-Length" in r.headers
        assert "ETag" in r.headers

    def test_delete_object(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/delcontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        data = b"delete me"
        httpx.put(
            f"{SWIFT_URL}/v1/{account_id}/delcontainer/delobj",
            headers={"X-Auth-Token": token},
            content=data,
            timeout=5,
        )
        r = httpx.delete(
            f"{SWIFT_URL}/v1/{account_id}/delcontainer/delobj",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 204
        r2 = httpx.get(
            f"{SWIFT_URL}/v1/{account_id}/delcontainer/delobj",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 404

    def test_delete_container(self, server_process, token, account_id):
        httpx.put(f"{SWIFT_URL}/v1/{account_id}/emptycontainer",
            headers={"X-Auth-Token": token}, timeout=5)
        r = httpx.delete(
            f"{SWIFT_URL}/v1/{account_id}/emptycontainer",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 204
