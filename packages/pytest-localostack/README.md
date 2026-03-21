# pytest-localostack

Pytest plugin for [LocalOStack](https://github.com/jaehanbyun/localostack) — provides fixtures that automatically start a LocalOStack server and create authenticated OpenStack connections for your tests.

## Installation

```bash
pip install pytest-localostack
```

## Quick Start

The plugin registers automatically via pytest's entry point system. Simply use the provided fixtures in your tests:

```python
def test_create_server(openstack_connection):
    server = openstack_connection.compute.create_server(
        name="test-vm",
        flavor_id="1",
        image_id="cirros",
    )
    assert server.name == "test-vm"
```

Or use the lower-level `localostack` fixture for direct URL access:

```python
import httpx

def test_keystone_versions(localostack):
    resp = httpx.get(f"{localostack['keystone']}/v3")
    assert resp.status_code == 200
```

## Fixtures

### `localostack` (session scope)

Starts a LocalOStack server as a subprocess and yields a dict of service URLs:

```python
{
    "keystone": "http://localhost:<port>",
    "nova": "http://localhost:<port>",
    "neutron": "http://localhost:<port>",
    "glance": "http://localhost:<port>",
    "cinder": "http://localhost:<port>",
    "placement": "http://localhost:<port>",
    "heat": "http://localhost:<port>",
    "swift": "http://localhost:<port>",
    "barbican": "http://localhost:<port>",
    "octavia": "http://localhost:<port>",
    "admin": "http://localhost:<port>",
    "auth_url": "http://localhost:<port>/v3",
}
```

The server is automatically stopped on teardown.

### `openstack_connection` (session scope)

Creates an authenticated `openstack.Connection` pointing at the LocalOStack server. Depends on the `localostack` fixture.

## Features

- **Random port allocation** — each test session gets unique ports, enabling safe parallel execution with pytest-xdist.
- **Automatic cleanup** — the server process receives SIGTERM on teardown, with a SIGKILL fallback after 5 seconds.
- **Crash detection** — if the server process exits unexpectedly during startup, the test fails immediately with captured stdout/stderr.
- **Health polling** — waits up to 30 seconds for the server to become ready before running tests.

## Requirements

- Python >= 3.11
- `localostack` must be installed (the server itself)
- `openstacksdk >= 4.0.0`
