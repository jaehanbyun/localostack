"""Placement API integration tests."""

import os
import subprocess
import time

import httpx
import pytest

KEYSTONE_PORT = 25300
NOVA_PORT = 28830
NEUTRON_PORT = 29750
GLANCE_PORT = 29350
CINDER_PORT = 28831
PLACEMENT_PORT = 28832
HEAT_PORT = 28833
SWIFT_PORT = 28857
ADMIN_PORT = 29901

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
PLACEMENT_URL = f"http://localhost:{PLACEMENT_PORT}"


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
        "LOCALOSTACK_ADMIN_PORT": str(ADMIN_PORT),
        "LOCALOSTACK_HOST": "127.0.0.1",
        "LOCALOSTACK_ENDPOINT_HOST": "localhost",
    })
    proc = subprocess.Popen(
        ["uv", "run", "localostack"], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
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
    r = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json={
        "auth": {
            "identity": {"methods": ["password"], "password": {"user": {
                "name": "admin", "password": "password", "domain": {"name": "Default"}}}},
            "scope": {"project": {"name": "admin", "domain": {"name": "Default"}}},
        }}, timeout=5)
    return r.headers["X-Subject-Token"]


class TestPlacementAPI:
    def test_version_discovery(self, server_process):
        r = httpx.get(f"{PLACEMENT_URL}/", timeout=5)
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert len(versions) >= 1
        v = versions[0]
        assert "max_version" in v
        assert "min_version" in v

    def test_placement_in_keystone_catalog(self, token):
        r = httpx.get(f"{KEYSTONE_URL}/v3/auth/catalog",
            headers={"X-Auth-Token": token}, timeout=5)
        catalog = r.json()["catalog"]
        types = [s["type"] for s in catalog]
        assert "placement" in types

    def test_list_resource_providers(self, server_process, token):
        r = httpx.get(f"{PLACEMENT_URL}/resource_providers",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        providers = r.json()["resource_providers"]
        assert len(providers) >= 1
        names = [p["name"] for p in providers]
        assert "localostack" in names

    def test_get_default_provider(self, server_process, token):
        r = httpx.get(f"{PLACEMENT_URL}/resource_providers",
            headers={"X-Auth-Token": token}, timeout=5)
        rp = r.json()["resource_providers"][0]
        rp_uuid = rp["uuid"]

        r2 = httpx.get(f"{PLACEMENT_URL}/resource_providers/{rp_uuid}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r2.status_code == 200
        assert r2.json()["name"] == "localostack"

    def test_get_inventories(self, server_process, token):
        r = httpx.get(f"{PLACEMENT_URL}/resource_providers",
            headers={"X-Auth-Token": token}, timeout=5)
        rp_uuid = r.json()["resource_providers"][0]["uuid"]

        r2 = httpx.get(f"{PLACEMENT_URL}/resource_providers/{rp_uuid}/inventories",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r2.status_code == 200
        invs = r2.json()["inventories"]
        assert "VCPU" in invs
        assert "MEMORY_MB" in invs
        assert "DISK_GB" in invs
        assert invs["VCPU"]["total"] > 0

    def test_allocation_candidates(self, server_process, token):
        r = httpx.get(
            f"{PLACEMENT_URL}/allocation_candidates?resources=VCPU:1,MEMORY_MB:512,DISK_GB:10",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert len(data["allocation_requests"]) >= 1
        assert len(data["provider_summaries"]) >= 1

    def test_allocation_lifecycle(self, server_process, token):
        import uuid as uuid_mod
        consumer_uuid = str(uuid_mod.uuid4())

        # Get provider uuid
        r = httpx.get(f"{PLACEMENT_URL}/resource_providers",
            headers={"X-Auth-Token": token}, timeout=5)
        rp_uuid = r.json()["resource_providers"][0]["uuid"]

        # Set allocations
        r2 = httpx.put(
            f"{PLACEMENT_URL}/allocations/{consumer_uuid}",
            headers={"X-Auth-Token": token},
            json={
                "allocations": [{"resource_provider": {"uuid": rp_uuid},
                                 "resources": {"VCPU": 2, "MEMORY_MB": 1024}}],
                "project_id": "test-project",
                "user_id": "test-user",
            }, timeout=5)
        assert r2.status_code == 204

        # Get allocations
        r3 = httpx.get(f"{PLACEMENT_URL}/allocations/{consumer_uuid}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r3.status_code == 200
        allocs = r3.json()["allocations"]
        assert rp_uuid in allocs
        assert allocs[rp_uuid]["resources"]["VCPU"] == 2

        # Delete allocations
        r4 = httpx.delete(f"{PLACEMENT_URL}/allocations/{consumer_uuid}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r4.status_code == 204

        # Verify deleted
        r5 = httpx.get(f"{PLACEMENT_URL}/allocations/{consumer_uuid}",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r5.json()["allocations"] == {}

    def test_usages(self, server_process, token):
        r = httpx.get(f"{PLACEMENT_URL}/usages",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        assert "usages" in r.json()
