"""Heat (Orchestration) API integration tests."""

import os
import subprocess
import time

import httpx
import pytest

KEYSTONE_PORT = 25400
NOVA_PORT = 28840
NEUTRON_PORT = 29760
GLANCE_PORT = 29360
CINDER_PORT = 28841
PLACEMENT_PORT = 28842
HEAT_PORT = 28843
ADMIN_PORT = 29902

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
HEAT_URL = f"http://localhost:{HEAT_PORT}"


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


@pytest.fixture(scope="module")
def tenant_id(token):
    r = httpx.get(f"{KEYSTONE_URL}/v3/auth/projects",
        headers={"X-Auth-Token": token}, timeout=5)
    projects = r.json().get("projects", [])
    if projects:
        return projects[0]["id"]
    return "admin"


SAMPLE_TEMPLATE = {
    "heat_template_version": "2018-08-31",
    "description": "Test stack",
    "resources": {
        "my_server": {
            "type": "OS::Nova::Server",
            "properties": {
                "image": "cirros",
                "flavor": "m1.tiny",
            },
        },
        "my_net": {
            "type": "OS::Neutron::Net",
            "properties": {
                "name": "test-net",
            },
        },
    },
}


class TestHeatAPI:
    def test_version_discovery(self, server_process):
        r = httpx.get(f"{HEAT_URL}/", timeout=5)
        assert r.status_code == 200
        versions = r.json()["versions"]
        assert len(versions) >= 1
        assert versions[0]["id"] == "v1.0"
        assert versions[0]["status"] == "CURRENT"

    def test_list_stacks_empty(self, server_process, token, tenant_id):
        r = httpx.get(f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token}, timeout=5)
        assert r.status_code == 200
        assert r.json()["stacks"] == []

    def test_create_stack(self, server_process, token, tenant_id):
        r = httpx.post(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            json={
                "stack_name": "test-stack",
                "template": SAMPLE_TEMPLATE,
                "parameters": {},
            },
            timeout=5,
        )
        assert r.status_code == 201
        data = r.json()
        assert "stack" in data
        assert "id" in data["stack"]
        assert "links" in data["stack"]

    def test_get_stack_detail(self, server_process, token, tenant_id):
        # First create a stack
        r = httpx.post(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            json={"stack_name": "detail-stack", "template": SAMPLE_TEMPLATE},
            timeout=5,
        )
        assert r.status_code == 201
        stack_id = r.json()["stack"]["id"]

        # Get detail by name/id
        r2 = httpx.get(
            f"{HEAT_URL}/v1/{tenant_id}/stacks/detail-stack/{stack_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        stack = r2.json()["stack"]
        assert stack["id"] == stack_id
        assert stack["stack_name"] == "detail-stack"
        assert stack["stack_status"] == "CREATE_COMPLETE"
        assert "stack_status_reason" in stack

    def test_list_stacks(self, server_process, token, tenant_id):
        # Ensure at least one stack is listed
        r = httpx.get(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 200
        stacks = r.json()["stacks"]
        assert len(stacks) >= 1
        # All visible stacks should not have DELETE_COMPLETE status
        for s in stacks:
            assert s["stack_status"] != "DELETE_COMPLETE"

    def test_list_resources(self, server_process, token, tenant_id):
        # Create stack with known template
        r = httpx.post(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            json={"stack_name": "resource-stack", "template": SAMPLE_TEMPLATE},
            timeout=5,
        )
        assert r.status_code == 201
        stack_id = r.json()["stack"]["id"]

        r2 = httpx.get(
            f"{HEAT_URL}/v1/{tenant_id}/stacks/resource-stack/{stack_id}/resources",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 200
        resources = r2.json()["resources"]
        assert len(resources) == 2  # my_server + my_net
        names = {res["resource_name"] for res in resources}
        assert "my_server" in names
        assert "my_net" in names
        for res in resources:
            assert res["resource_status"] == "CREATE_COMPLETE"
            assert "physical_resource_id" in res
            assert "logical_resource_id" in res

    def test_delete_stack(self, server_process, token, tenant_id):
        # Create stack
        r = httpx.post(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            json={"stack_name": "delete-stack", "template": {}},
            timeout=5,
        )
        assert r.status_code == 201
        stack_id = r.json()["stack"]["id"]

        # Delete stack
        r2 = httpx.delete(
            f"{HEAT_URL}/v1/{tenant_id}/stacks/delete-stack/{stack_id}",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r2.status_code == 204

        # Verify stack is not in the list
        r3 = httpx.get(
            f"{HEAT_URL}/v1/{tenant_id}/stacks",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        visible_ids = [s["id"] for s in r3.json()["stacks"]]
        assert stack_id not in visible_ids

    def test_resource_types(self, server_process, token, tenant_id):
        r = httpx.get(
            f"{HEAT_URL}/v1/{tenant_id}/resource_types",
            headers={"X-Auth-Token": token},
            timeout=5,
        )
        assert r.status_code == 200
        types = r.json()["resource_types"]
        assert len(types) > 0
        assert "OS::Nova::Server" in types
        assert "OS::Neutron::Net" in types
        assert "OS::Heat::Stack" in types
