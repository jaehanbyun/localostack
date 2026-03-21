"""Octavia Load Balancer API integration tests."""

import os
import pathlib
import subprocess
import time

import httpx
import pytest

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent.parent)

KEYSTONE_PORT = 25700
NOVA_PORT = 28870
NEUTRON_PORT = 29790
GLANCE_PORT = 29390
CINDER_PORT = 28871
PLACEMENT_PORT = 28872
HEAT_PORT = 28873
SWIFT_PORT = 28874
BARBICAN_PORT = 28875
OCTAVIA_PORT = 29877
ADMIN_PORT = 29908

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
OCTAVIA_URL = f"http://localhost:{OCTAVIA_PORT}"


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
        ["uv", "run", "localostack", "start"], env=env,
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


class TestOctaviaAPI:
    def test_version_discovery(self, server_process):
        r = httpx.get(f"{OCTAVIA_URL}/", timeout=5)
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert len(versions) >= 1
        assert versions[0]["id"] == "v2.0"
        assert versions[0]["status"] == "CURRENT"

    def test_list_loadbalancers_empty(self, server_process, token):
        r = httpx.get(f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        assert r.json()["loadbalancers"] == []

    def test_create_loadbalancer(self, server_process, token):
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {
                "name": "test-lb",
                "vip_address": "192.168.0.10",
                "description": "test load balancer",
            }},
            timeout=5,
        )
        assert r.status_code == 201
        data = r.json()
        assert "loadbalancer" in data
        lb = data["loadbalancer"]
        assert "id" in lb
        assert lb["name"] == "test-lb"
        assert lb["provisioning_status"] == "ACTIVE"
        assert lb["vip_address"] == "192.168.0.10"

    def test_get_loadbalancer(self, server_process, token):
        # Create a load balancer first
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {"name": "get-lb"}},
            timeout=5,
        )
        assert r.status_code == 201
        lb_id = r.json()["loadbalancer"]["id"]

        # Get it by ID
        r2 = httpx.get(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers/{lb_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        lb = r2.json()["loadbalancer"]
        assert lb["id"] == lb_id
        assert lb["name"] == "get-lb"
        assert lb["provisioning_status"] == "ACTIVE"

    def test_create_listener(self, server_process, token):
        # Create a load balancer first
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {"name": "listener-lb"}},
            timeout=5,
        )
        assert r.status_code == 201
        lb_id = r.json()["loadbalancer"]["id"]

        # Create a listener
        r2 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/listeners",
            headers={"X-Auth-Token": token},
            json={"listener": {
                "name": "test-listener",
                "loadbalancer_id": lb_id,
                "protocol": "HTTP",
                "protocol_port": 80,
            }},
            timeout=5,
        )
        assert r2.status_code == 201
        data = r2.json()
        assert "listener" in data
        ln = data["listener"]
        assert "id" in ln
        assert ln["name"] == "test-listener"
        assert ln["protocol"] == "HTTP"
        assert ln["protocol_port"] == 80
        assert ln["provisioning_status"] == "ACTIVE"

    def test_create_pool(self, server_process, token):
        # Create lb + listener
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {"name": "pool-lb"}},
            timeout=5,
        )
        assert r.status_code == 201
        lb_id = r.json()["loadbalancer"]["id"]

        r2 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/listeners",
            headers={"X-Auth-Token": token},
            json={"listener": {
                "name": "pool-listener",
                "loadbalancer_id": lb_id,
                "protocol": "HTTP",
                "protocol_port": 8080,
            }},
            timeout=5,
        )
        assert r2.status_code == 201
        listener_id = r2.json()["listener"]["id"]

        # Create pool
        r3 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/pools",
            headers={"X-Auth-Token": token},
            json={"pool": {
                "name": "test-pool",
                "listener_id": listener_id,
                "loadbalancer_id": lb_id,
                "protocol": "HTTP",
                "lb_algorithm": "ROUND_ROBIN",
            }},
            timeout=5,
        )
        assert r3.status_code == 201
        data = r3.json()
        assert "pool" in data
        pool = data["pool"]
        assert "id" in pool
        assert pool["name"] == "test-pool"
        assert pool["lb_algorithm"] == "ROUND_ROBIN"
        assert pool["provisioning_status"] == "ACTIVE"

    def test_create_and_list_members(self, server_process, token):
        # Create lb + listener + pool
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {"name": "member-lb"}},
            timeout=5,
        )
        lb_id = r.json()["loadbalancer"]["id"]

        r2 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/listeners",
            headers={"X-Auth-Token": token},
            json={"listener": {
                "name": "member-listener",
                "loadbalancer_id": lb_id,
                "protocol": "HTTP",
                "protocol_port": 80,
            }},
            timeout=5,
        )
        listener_id = r2.json()["listener"]["id"]

        r3 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/pools",
            headers={"X-Auth-Token": token},
            json={"pool": {
                "name": "member-pool",
                "listener_id": listener_id,
                "loadbalancer_id": lb_id,
                "protocol": "HTTP",
                "lb_algorithm": "ROUND_ROBIN",
            }},
            timeout=5,
        )
        pool_id = r3.json()["pool"]["id"]

        # Create a member
        r4 = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/pools/{pool_id}/members",
            headers={"X-Auth-Token": token},
            json={"member": {
                "name": "test-member",
                "address": "10.0.0.5",
                "protocol_port": 8080,
                "weight": 2,
            }},
            timeout=5,
        )
        assert r4.status_code == 201
        m = r4.json()["member"]
        assert m["address"] == "10.0.0.5"
        assert m["protocol_port"] == 8080
        assert m["weight"] == 2

        # List members
        r5 = httpx.get(
            f"{OCTAVIA_URL}/v2/lbaas/pools/{pool_id}/members",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r5.status_code == 200
        members = r5.json()["members"]
        assert len(members) == 1
        assert members[0]["address"] == "10.0.0.5"

    def test_delete_loadbalancer(self, server_process, token):
        # Create a load balancer
        r = httpx.post(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers",
            headers={"X-Auth-Token": token},
            json={"loadbalancer": {"name": "delete-lb"}},
            timeout=5,
        )
        assert r.status_code == 201
        lb_id = r.json()["loadbalancer"]["id"]

        # Delete it
        r2 = httpx.delete(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers/{lb_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 204

        # Verify it's gone
        r3 = httpx.get(
            f"{OCTAVIA_URL}/v2/lbaas/loadbalancers/{lb_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r3.status_code == 404
