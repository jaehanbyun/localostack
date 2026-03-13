"""Smoke tests using openstacksdk against a running LocalOStack server."""

import subprocess
import time
import os

import httpx
import openstack
import pytest

KEYSTONE_PORT = 25000
NOVA_PORT = 28774
NEUTRON_PORT = 29696
GLANCE_PORT = 29292
CINDER_PORT = 28776
PLACEMENT_PORT = 28990
HEAT_PORT = 28993
SWIFT_PORT = 28855
BARBICAN_PORT = 29313
OCTAVIA_PORT = 29878
ADMIN_PORT = 29900

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"


@pytest.fixture(scope="module")
def server_process():
    env = os.environ.copy()
    env["LOCALOSTACK_KEYSTONE_PORT"] = str(KEYSTONE_PORT)
    env["LOCALOSTACK_NOVA_PORT"] = str(NOVA_PORT)
    env["LOCALOSTACK_NEUTRON_PORT"] = str(NEUTRON_PORT)
    env["LOCALOSTACK_GLANCE_PORT"] = str(GLANCE_PORT)
    env["LOCALOSTACK_CINDER_PORT"] = str(CINDER_PORT)
    env["LOCALOSTACK_PLACEMENT_PORT"] = str(PLACEMENT_PORT)
    env["LOCALOSTACK_HEAT_PORT"] = str(HEAT_PORT)
    env["LOCALOSTACK_SWIFT_PORT"] = str(SWIFT_PORT)
    env["LOCALOSTACK_BARBICAN_PORT"] = str(BARBICAN_PORT)
    env["LOCALOSTACK_OCTAVIA_PORT"] = str(OCTAVIA_PORT)
    env["LOCALOSTACK_ADMIN_PORT"] = str(ADMIN_PORT)
    env["LOCALOSTACK_HOST"] = "127.0.0.1"
    env["LOCALOSTACK_ENDPOINT_HOST"] = "localhost"

    proc = subprocess.Popen(
        ["uv", "run", "localostack"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="/Users/byeonjaehan/projects/localostack",
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


@pytest.fixture(scope="module")
def conn(server_process):
    return openstack.connect(
        auth_url=f"http://localhost:{KEYSTONE_PORT}/v3",
        project_name="admin",
        username="admin",
        password="password",
        user_domain_name="Default",
        project_domain_name="Default",
        load_yaml_config=False,
        load_envvars=False,
    )


class TestKeystoneSDK:
    def test_list_projects(self, conn):
        projects = list(conn.identity.projects())
        assert len(projects) >= 1
        names = [p.name for p in projects]
        assert "admin" in names

    def test_list_users(self, conn):
        users = list(conn.identity.users())
        assert len(users) >= 1
        names = [u.name for u in users]
        assert "admin" in names


class TestGlanceSDK:
    def test_list_images(self, conn):
        images = list(conn.image.images())
        assert len(images) >= 1
        names = [i.name for i in images]
        assert "cirros-0.6.2" in names


class TestNeutronSDK:
    def test_list_networks(self, conn):
        networks = list(conn.network.networks())
        assert len(networks) >= 1
        names = [n.name for n in networks]
        assert "public" in names

    def test_list_security_groups(self, conn):
        sgs = list(conn.network.security_groups())
        assert len(sgs) >= 1


class TestNovaSDK:
    def test_list_flavors(self, conn):
        flavors = list(conn.compute.flavors())
        assert len(flavors) >= 1
        names = [f.name for f in flavors]
        assert "m1.tiny" in names

    def test_server_lifecycle(self, conn):
        # Get a real image ID from Glance
        images = list(conn.image.images())
        assert images, "No images available"
        image_id = images[0].id

        # Create
        server = conn.compute.create_server(
            name="sdk-test-vm",
            flavor_id="1",
            image_id=image_id,
            networks="none",
        )
        assert server.name == "sdk-test-vm"
        assert server.status in ("ACTIVE", "BUILD")

        # List
        servers = list(conn.compute.servers())
        ids = [s.id for s in servers]
        assert server.id in ids

        # Delete
        conn.compute.delete_server(server.id)


class TestNovaMicroversion:
    """Validate microversion negotiation and 2.47 flavor object behavior."""

    def test_version_discovery_reports_max(self, server_process):
        r = httpx.get(f"http://localhost:{NOVA_PORT}/")
        assert r.status_code == 200
        versions = r.json()["versions"]
        v = versions[0]
        assert v["version"] == "2.47"
        assert v["min_version"] == "2.1"

    def test_default_response_header_is_min_version(self, server_process, conn):
        token = conn.auth_token
        r = httpx.get(
            f"http://localhost:{NOVA_PORT}/v2.1/flavors",
            headers={"X-Auth-Token": token},
        )
        assert r.headers["X-OpenStack-Nova-API-Version"] == "2.1"

    def test_echoes_requested_microversion(self, server_process, conn):
        token = conn.auth_token
        r = httpx.get(
            f"http://localhost:{NOVA_PORT}/v2.1/flavors",
            headers={"X-Auth-Token": token, "X-OpenStack-Nova-API-Version": "2.30"},
        )
        assert r.headers["X-OpenStack-Nova-API-Version"] == "2.30"

    def test_latest_resolves_to_max(self, server_process, conn):
        token = conn.auth_token
        r = httpx.get(
            f"http://localhost:{NOVA_PORT}/v2.1/flavors",
            headers={"X-Auth-Token": token, "X-OpenStack-Nova-API-Version": "latest"},
        )
        assert r.headers["X-OpenStack-Nova-API-Version"] == "2.47"

    def test_over_max_clamped_to_max(self, server_process, conn):
        token = conn.auth_token
        r = httpx.get(
            f"http://localhost:{NOVA_PORT}/v2.1/flavors",
            headers={"X-Auth-Token": token, "X-OpenStack-Nova-API-Version": "2.99"},
        )
        assert r.headers["X-OpenStack-Nova-API-Version"] == "2.47"

    def test_flavor_id_only_at_microversion_2_1(self, server_process, conn):
        images = list(conn.image.images())
        server = conn.compute.create_server(name="mv-test-vm", flavor_id="1", image_id=images[0].id, networks="none")
        token = conn.auth_token
        try:
            r = httpx.get(
                f"http://localhost:{NOVA_PORT}/v2.1/servers/{server.id}",
                headers={"X-Auth-Token": token, "X-OpenStack-Nova-API-Version": "2.1"},
            )
            assert r.status_code == 200
            flavor = r.json()["server"]["flavor"]
            assert "id" in flavor
            assert "vcpus" not in flavor
        finally:
            conn.compute.delete_server(server.id)

    def test_full_flavor_object_at_microversion_2_47(self, server_process, conn):
        images = list(conn.image.images())
        server = conn.compute.create_server(name="mv-test-vm-247", flavor_id="1", image_id=images[0].id, networks="none")
        token = conn.auth_token
        try:
            r = httpx.get(
                f"http://localhost:{NOVA_PORT}/v2.1/servers/{server.id}",
                headers={"X-Auth-Token": token, "X-OpenStack-Nova-API-Version": "2.47"},
            )
            assert r.status_code == 200
            flavor = r.json()["server"]["flavor"]
            assert "vcpus" in flavor
            assert "ram" in flavor
            assert "disk" in flavor
        finally:
            conn.compute.delete_server(server.id)


class TestCinderSDK:
    def test_list_volume_types(self, conn):
        types = list(conn.block_storage.types())
        assert len(types) >= 1
        names = [t.name for t in types]
        assert "__DEFAULT__" in names

    def test_volume_lifecycle(self, conn):
        # Create
        vol = conn.block_storage.create_volume(name="sdk-test-vol", size=1)
        assert vol.name == "sdk-test-vol"
        assert vol.size == 1
        assert vol.status in ("available", "creating")

        # List
        vols = list(conn.block_storage.volumes())
        ids = [v.id for v in vols]
        assert vol.id in ids

        # Delete
        conn.block_storage.delete_volume(vol.id)
