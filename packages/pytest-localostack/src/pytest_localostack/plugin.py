"""Core pytest plugin providing LocalOStack fixtures."""

from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
from typing import Generator

import httpx
import pytest


def _find_free_port() -> int:
    """Find a free port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


_SERVICE_PORTS = [
    ("KEYSTONE", "keystone_port"),
    ("NOVA", "nova_port"),
    ("NEUTRON", "neutron_port"),
    ("GLANCE", "glance_port"),
    ("CINDER", "cinder_port"),
    ("PLACEMENT", "placement_port"),
    ("HEAT", "heat_port"),
    ("SWIFT", "swift_port"),
    ("BARBICAN", "barbican_port"),
    ("OCTAVIA", "octavia_port"),
    ("ADMIN", "admin_port"),
]


@pytest.fixture(scope="session")
def localostack() -> Generator[dict, None, None]:
    """Start a LocalOStack server and yield service URLs.

    The server runs as a subprocess with random ports to support
    parallel test execution (pytest-xdist).
    """
    ports: dict[str, int] = {}
    env = os.environ.copy()
    env["LOCALOSTACK_HOST"] = "127.0.0.1"
    env["LOCALOSTACK_ENDPOINT_HOST"] = "localhost"

    for env_suffix, _ in _SERVICE_PORTS:
        port = _find_free_port()
        ports[env_suffix.lower()] = port
        env[f"LOCALOSTACK_{env_suffix}_PORT"] = str(port)

    proc = subprocess.Popen(
        [sys.executable, "-m", "localostack.cli.main", "start"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready (poll Keystone health)
    keystone_url = f"http://localhost:{ports['keystone']}"
    deadline = time.monotonic() + 30
    ready = False

    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{keystone_url}/", timeout=2)
            if resp.status_code < 500:
                ready = True
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            pass

        # Check if process crashed
        if proc.poll() is not None:
            stdout = proc.stdout.read().decode() if proc.stdout else ""
            stderr = proc.stderr.read().decode() if proc.stderr else ""
            pytest.fail(
                f"LocalOStack failed to start (exit code {proc.returncode}).\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )

        time.sleep(0.5)

    if not ready:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        pytest.fail("LocalOStack failed to start within 30 seconds")

    # Build service URLs
    urls = {
        "keystone": f"http://localhost:{ports['keystone']}",
        "nova": f"http://localhost:{ports['nova']}",
        "neutron": f"http://localhost:{ports['neutron']}",
        "glance": f"http://localhost:{ports['glance']}",
        "cinder": f"http://localhost:{ports['cinder']}",
        "placement": f"http://localhost:{ports['placement']}",
        "heat": f"http://localhost:{ports['heat']}",
        "swift": f"http://localhost:{ports['swift']}",
        "barbican": f"http://localhost:{ports['barbican']}",
        "octavia": f"http://localhost:{ports['octavia']}",
        "admin": f"http://localhost:{ports['admin']}",
        "auth_url": f"http://localhost:{ports['keystone']}/v3",
    }

    yield urls

    # Teardown: SIGTERM → 5s → SIGKILL
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture(scope="session")
def openstack_connection(localostack):
    """Create an authenticated OpenStack connection to LocalOStack."""
    import openstack

    conn = openstack.connect(
        auth_url=localostack["auth_url"],
        project_name="admin",
        username="admin",
        password="password",
        user_domain_name="Default",
        project_domain_name="Default",
        region_name="RegionOne",
    )
    yield conn
    conn.close()
