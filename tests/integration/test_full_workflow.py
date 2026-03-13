import os
import pathlib
import subprocess
import time

import httpx
import pytest

_PROJECT_ROOT = str(pathlib.Path(__file__).resolve().parent.parent.parent)

KEYSTONE_PORT = 15000
NOVA_PORT = 18774
NEUTRON_PORT = 19696
GLANCE_PORT = 19292
HEAT_PORT = 18004
SWIFT_PORT = 28859
BARBICAN_PORT = 29318
OCTAVIA_PORT = 29884

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"
NOVA_URL = f"http://localhost:{NOVA_PORT}"
NEUTRON_URL = f"http://localhost:{NEUTRON_PORT}"
GLANCE_URL = f"http://localhost:{GLANCE_PORT}"

AUTH_BODY = {
    "auth": {
        "identity": {
            "methods": ["password"],
            "password": {
                "user": {
                    "name": "admin",
                    "domain": {"id": "default"},
                    "password": "password",
                }
            },
        },
        "scope": {
            "project": {
                "name": "admin",
                "domain": {"id": "default"},
            }
        },
    }
}


@pytest.fixture(scope="session")
def server_process():
    env = os.environ.copy()
    env["LOCALOSTACK_KEYSTONE_PORT"] = str(KEYSTONE_PORT)
    env["LOCALOSTACK_NOVA_PORT"] = str(NOVA_PORT)
    env["LOCALOSTACK_NEUTRON_PORT"] = str(NEUTRON_PORT)
    env["LOCALOSTACK_GLANCE_PORT"] = str(GLANCE_PORT)
    env["LOCALOSTACK_HEAT_PORT"] = str(HEAT_PORT)
    env["LOCALOSTACK_SWIFT_PORT"] = str(SWIFT_PORT)
    env["LOCALOSTACK_BARBICAN_PORT"] = str(BARBICAN_PORT)
    env["LOCALOSTACK_OCTAVIA_PORT"] = str(OCTAVIA_PORT)
    env["LOCALOSTACK_HOST"] = "127.0.0.1"
    env["LOCALOSTACK_ENDPOINT_HOST"] = "localhost"

    proc = subprocess.Popen(
        ["uv", "run", "localostack"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=_PROJECT_ROOT,
    )

    for _ in range(30):
        try:
            httpx.get(f"{KEYSTONE_URL}/")
            break
        except httpx.ConnectError:
            time.sleep(0.5)
    else:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise RuntimeError(
            f"Server failed to start.\nstdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield proc
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def token(server_process):
    resp = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json=AUTH_BODY)
    assert resp.status_code == 201
    return resp.headers["X-Subject-Token"]


def headers(token: str) -> dict:
    return {"X-Auth-Token": token}


# ── Phase 1: Keystone Authentication ────────────────────────

class TestKeystoneAuth:
    def test_create_token(self, server_process):
        resp = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json=AUTH_BODY)
        assert resp.status_code == 201
        assert "X-Subject-Token" in resp.headers
        body = resp.json()
        assert "token" in body
        assert "catalog" in body["token"]
        assert "user" in body["token"]
        assert body["token"]["user"]["name"] == "admin"

    def test_token_has_catalog_with_services(self, server_process):
        resp = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json=AUTH_BODY)
        catalog = resp.json()["token"]["catalog"]
        service_types = {svc["type"] for svc in catalog}
        assert "identity" in service_types
        assert "compute" in service_types
        assert "network" in service_types
        assert "image" in service_types

    def test_validate_token(self, token):
        resp = httpx.get(
            f"{KEYSTONE_URL}/v3/auth/tokens",
            headers={**headers(token), "X-Subject-Token": token},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token"]["user"]["name"] == "admin"


# ── Phase 2: Keystone CRUD ──────────────────────────────────

class TestKeystoneCRUD:
    def test_create_user(self, token):
        resp = httpx.post(
            f"{KEYSTONE_URL}/v3/users",
            json={"user": {"name": "testuser", "password": "testpass", "domain_id": "default"}},
            headers=headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["user"]["name"] == "testuser"

    def test_list_users(self, token):
        resp = httpx.get(f"{KEYSTONE_URL}/v3/users", headers=headers(token))
        assert resp.status_code == 200
        names = [u["name"] for u in resp.json()["users"]]
        assert "admin" in names
        assert "testuser" in names

    def test_create_project(self, token):
        resp = httpx.post(
            f"{KEYSTONE_URL}/v3/projects",
            json={"project": {"name": "testproject", "domain_id": "default"}},
            headers=headers(token),
        )
        assert resp.status_code == 201
        assert resp.json()["project"]["name"] == "testproject"

    def test_list_projects(self, token):
        resp = httpx.get(f"{KEYSTONE_URL}/v3/projects", headers=headers(token))
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()["projects"]]
        assert "admin" in names
        assert "testproject" in names

    def test_list_services(self, token):
        resp = httpx.get(f"{KEYSTONE_URL}/v3/services", headers=headers(token))
        assert resp.status_code == 200
        services = resp.json()["services"]
        assert len(services) >= 4
        types = {s["type"] for s in services}
        assert "identity" in types
        assert "compute" in types

    def test_list_endpoints(self, token):
        resp = httpx.get(f"{KEYSTONE_URL}/v3/endpoints", headers=headers(token))
        assert resp.status_code == 200
        endpoints = resp.json()["endpoints"]
        assert len(endpoints) >= 12  # 4 services * 3 interfaces


# ── Phase 3: Glance Images ──────────────────────────────────

class TestGlanceImages:
    def test_list_images_has_cirros(self, token):
        resp = httpx.get(f"{GLANCE_URL}/v2/images", headers=headers(token))
        assert resp.status_code == 200
        images = resp.json()["images"]
        names = [img["name"] for img in images]
        assert "cirros-0.6.2" in names

    def test_create_image(self, token):
        resp = httpx.post(
            f"{GLANCE_URL}/v2/images",
            json={
                "name": "test-image",
                "container_format": "bare",
                "disk_format": "raw",
                "visibility": "private",
            },
            headers=headers(token),
        )
        assert resp.status_code == 201
        img = resp.json()
        assert img["name"] == "test-image"
        assert img["status"] == "queued"

    def test_upload_and_download_image(self, token):
        create_resp = httpx.post(
            f"{GLANCE_URL}/v2/images",
            json={
                "name": "upload-test",
                "container_format": "bare",
                "disk_format": "raw",
            },
            headers=headers(token),
        )
        image_id = create_resp.json()["id"]

        test_data = b"Hello LocalOStack Image Data!"
        upload_resp = httpx.put(
            f"{GLANCE_URL}/v2/images/{image_id}/file",
            content=test_data,
            headers={**headers(token), "Content-Type": "application/octet-stream"},
        )
        assert upload_resp.status_code == 204

        get_resp = httpx.get(
            f"{GLANCE_URL}/v2/images/{image_id}",
            headers=headers(token),
        )
        assert get_resp.status_code == 200
        img = get_resp.json()
        assert img["status"] == "active"
        assert img["size"] == len(test_data)
        assert img["checksum"] is not None

        download_resp = httpx.get(
            f"{GLANCE_URL}/v2/images/{image_id}/file",
            headers=headers(token),
        )
        assert download_resp.status_code == 200
        assert download_resp.content == test_data


# ── Phase 4: Neutron Networks ────────────────────────────────

class TestNeutronNetworks:
    def test_list_bootstrap_networks(self, token):
        resp = httpx.get(f"{NEUTRON_URL}/v2.0/networks", headers=headers(token))
        assert resp.status_code == 200
        names = [n["name"] for n in resp.json()["networks"]]
        assert "public" in names
        assert "private" in names

    def test_create_network(self, token):
        resp = httpx.post(
            f"{NEUTRON_URL}/v2.0/networks",
            json={"network": {"name": "test-net", "admin_state_up": True}},
            headers=headers(token),
        )
        assert resp.status_code == 201
        net = resp.json()["network"]
        assert net["name"] == "test-net"
        assert net["status"] == "ACTIVE"

    def test_create_subnet_and_check_network(self, token):
        net_resp = httpx.post(
            f"{NEUTRON_URL}/v2.0/networks",
            json={"network": {"name": "subnet-test-net"}},
            headers=headers(token),
        )
        net_id = net_resp.json()["network"]["id"]

        sub_resp = httpx.post(
            f"{NEUTRON_URL}/v2.0/subnets",
            json={
                "subnet": {
                    "name": "test-subnet",
                    "network_id": net_id,
                    "cidr": "10.100.0.0/24",
                    "ip_version": 4,
                }
            },
            headers=headers(token),
        )
        assert sub_resp.status_code == 201
        subnet = sub_resp.json()["subnet"]
        subnet_id = subnet["id"]
        assert subnet["cidr"] == "10.100.0.0/24"

        get_resp = httpx.get(
            f"{NEUTRON_URL}/v2.0/networks/{net_id}",
            headers=headers(token),
        )
        assert get_resp.status_code == 200
        net = get_resp.json()["network"]
        assert subnet_id in net["subnets"]

    def test_list_security_groups_has_default(self, token):
        resp = httpx.get(f"{NEUTRON_URL}/v2.0/security-groups", headers=headers(token))
        assert resp.status_code == 200
        names = [sg["name"] for sg in resp.json()["security_groups"]]
        assert "default" in names

    def test_create_port_auto_assigns_mac_ip(self, token):
        nets_resp = httpx.get(f"{NEUTRON_URL}/v2.0/networks", headers=headers(token))
        private_net = None
        for n in nets_resp.json()["networks"]:
            if n["name"] == "private":
                private_net = n
                break
        assert private_net is not None

        port_resp = httpx.post(
            f"{NEUTRON_URL}/v2.0/ports",
            json={"port": {"network_id": private_net["id"]}},
            headers=headers(token),
        )
        assert port_resp.status_code == 201
        port = port_resp.json()["port"]
        assert port["mac_address"].startswith("fa:16:3e:")
        assert len(port["fixed_ips"]) > 0
        assert "ip_address" in port["fixed_ips"][0]


# ── Phase 5: Nova Compute ───────────────────────────────────

class TestNovaCompute:
    def test_list_flavors(self, token):
        resp = httpx.get(f"{NOVA_URL}/v2.1/flavors/detail", headers=headers(token))
        assert resp.status_code == 200
        flavors = resp.json()["flavors"]
        assert len(flavors) >= 5
        names = [f["name"] for f in flavors]
        assert "m1.tiny" in names
        assert "m1.small" in names

    def test_create_keypair(self, token):
        resp = httpx.post(
            f"{NOVA_URL}/v2.1/os-keypairs",
            json={"keypair": {"name": "test-key", "type": "ssh"}},
            headers=headers(token),
        )
        assert resp.status_code == 200
        kp = resp.json()["keypair"]
        assert kp["name"] == "test-key"
        assert kp["fingerprint"] is not None

    def test_server_lifecycle(self, token):
        # Create
        create_resp = httpx.post(
            f"{NOVA_URL}/v2.1/servers",
            json={
                "server": {
                    "name": "test-vm",
                    "imageRef": "cirros",
                    "flavorRef": "1",
                }
            },
            headers=headers(token),
        )
        assert create_resp.status_code == 202
        server_id = create_resp.json()["server"]["id"]

        # Get -> ACTIVE
        get_resp = httpx.get(
            f"{NOVA_URL}/v2.1/servers/{server_id}",
            headers=headers(token),
        )
        assert get_resp.status_code == 200
        srv = get_resp.json()["server"]
        assert srv["status"] == "ACTIVE"

        # List detail
        list_resp = httpx.get(
            f"{NOVA_URL}/v2.1/servers/detail",
            headers=headers(token),
        )
        assert list_resp.status_code == 200
        ids = [s["id"] for s in list_resp.json()["servers"]]
        assert server_id in ids

        # Stop
        stop_resp = httpx.post(
            f"{NOVA_URL}/v2.1/servers/{server_id}/action",
            json={"os-stop": None},
            headers=headers(token),
        )
        assert stop_resp.status_code == 202

        get_resp2 = httpx.get(
            f"{NOVA_URL}/v2.1/servers/{server_id}",
            headers=headers(token),
        )
        assert get_resp2.json()["server"]["status"] == "SHUTOFF"

        # Start
        start_resp = httpx.post(
            f"{NOVA_URL}/v2.1/servers/{server_id}/action",
            json={"os-start": None},
            headers=headers(token),
        )
        assert start_resp.status_code == 202

        get_resp3 = httpx.get(
            f"{NOVA_URL}/v2.1/servers/{server_id}",
            headers=headers(token),
        )
        assert get_resp3.json()["server"]["status"] == "ACTIVE"

        # Delete
        del_resp = httpx.delete(
            f"{NOVA_URL}/v2.1/servers/{server_id}",
            headers=headers(token),
        )
        assert del_resp.status_code == 204

        # Confirm 404
        get_resp4 = httpx.get(
            f"{NOVA_URL}/v2.1/servers/{server_id}",
            headers=headers(token),
        )
        assert get_resp4.status_code == 404

    def test_get_limits(self, token):
        resp = httpx.get(f"{NOVA_URL}/v2.1/limits", headers=headers(token))
        assert resp.status_code == 200
        limits = resp.json()["limits"]
        assert "absolute" in limits
        assert "maxTotalInstances" in limits["absolute"]


# ── Phase 6: Token Revocation ────────────────────────────────

class TestTokenRevocation:
    def test_revoke_token_and_verify_401(self, server_process):
        resp = httpx.post(f"{KEYSTONE_URL}/v3/auth/tokens", json=AUTH_BODY)
        temp_token = resp.headers["X-Subject-Token"]

        del_resp = httpx.delete(
            f"{KEYSTONE_URL}/v3/auth/tokens",
            headers={
                "X-Auth-Token": temp_token,
                "X-Subject-Token": temp_token,
            },
        )
        assert del_resp.status_code == 204

        check_resp = httpx.get(
            f"{KEYSTONE_URL}/v3/users",
            headers={"X-Auth-Token": temp_token},
        )
        assert check_resp.status_code == 401
