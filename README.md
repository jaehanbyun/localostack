# ⚡ LocalOStack

> Local OpenStack API Emulator for development and CI/CD testing.

[![Tests](https://github.com/jaehanbyun/localostack/actions/workflows/test.yml/badge.svg)](https://github.com/jaehanbyun/localostack/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![GitHub Pages](https://img.shields.io/badge/docs-GitHub%20Pages-informational)](https://jaehanbyun.github.io/localostack/)

Run **10 OpenStack APIs** locally in a single process. Full API fidelity — no cloud account required.

📖 **[Documentation & Landing Page →](https://jaehanbyun.github.io/localostack/)**

---

## Services

| Service | Port | Description |
|---------|------|-------------|
| Keystone | 5000 | Identity & authentication |
| Nova | 8774 | Compute (microversion up to 2.47) |
| Neutron | 9696 | Network |
| Glance | 9292 | Image (cirros pre-loaded) |
| Cinder | 8776 | Block storage |
| Placement | 8778 | Resource placement |
| Heat | 8004 | Orchestration |
| Swift | 8080 | Object storage |
| Barbican | 9311 | Secret management |
| Octavia | 9876 | Load balancing |
| Admin | 9999 | Fault injection + dashboard |

## Quick Start

```bash
docker run --rm \
  -p 5000:5000 -p 8774:8774 -p 9696:9696 \
  -p 9292:9292 -p 8776:8776 -p 8778:8778 \
  -p 8004:8004 -p 8080:8080 -p 9311:9311 \
  -p 9876:9876 -p 9999:9999 \
  -e LOCALOSTACK_HOST=0.0.0.0 \
  localostack/localostack:latest
```

Then configure your client:

```yaml
# ~/.config/openstack/clouds.yaml
clouds:
  localostack:
    auth:
      auth_url: http://localhost:5000
      username: admin
      password: password
      project_name: admin
      user_domain_name: Default
      project_domain_name: Default
    region_name: RegionOne
```

```bash
openstack --os-cloud localostack server list
```

## Features

- **Zero Config** — works out of the box with default credentials
- **API Fidelity** — compatible with openstacksdk, python-openstackclient, Terraform, gophercloud
- **Fault Injection** — inject errors, delays, throttling via Admin API
- **SQLite Persistence** — survive restarts with `LOCALOSTACK_PERSISTENCE=sqlite`
- **Multi-Region** — configurable via `LOCALOSTACK_REGION`
- **106 integration tests** passing

## Development

```bash
# Install dependencies
uv sync

# Run all tests
uv run pytest tests/ -q

# Run locally
uv run localostack
```

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `LOCALOSTACK_PERSISTENCE` | `memory` | `memory` or `sqlite` |
| `LOCALOSTACK_DB_PATH` | `/var/lib/localostack/state.db` | SQLite path |
| `LOCALOSTACK_REGION` | `RegionOne` | Region name |
| `LOCALOSTACK_ADMIN_PASSWORD` | `password` | Admin password |
| `LOCALOSTACK_FAULT_RULES` | `""` | JSON fault rules |

See [full configuration docs](https://jaehanbyun.github.io/localostack/#config) for all options.

## License

MIT © 2024 jaehanbyun
