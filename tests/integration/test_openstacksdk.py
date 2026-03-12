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

KEYSTONE_URL = f"http://localhost:{KEYSTONE_PORT}"


@pytest.fixture(scope="module")
def server_process():
    env = os.environ.copy()
    env["LOCALOSTACK_KEYSTONE_PORT"] = str(KEYSTONE_PORT)
    env["LOCALOSTACK_NOVA_PORT"] = str(NOVA_PORT)
    env["LOCALOSTACK_NEUTRON_PORT"] = str(NEUTRON_PORT)
    env["LOCALOSTACK_GLANCE_PORT"] = str(GLANCE_PORT)
    env["LOCALOSTACK_CINDER_PORT"] = str(CINDER_PORT)
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
