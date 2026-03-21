import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.metadata import version as pkg_version
from pathlib import Path

import click

from localostack.core.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("localostack")

_VERSION = pkg_version("localostack")

# Service definitions: (name, port_attr, version_path)
_SERVICES = [
    ("Keystone", "keystone_port", "/v3"),
    ("Nova", "nova_port", "/v2.1"),
    ("Neutron", "neutron_port", "/v2.0"),
    ("Glance", "glance_port", "/v2"),
    ("Cinder", "cinder_port", "/v3"),
    ("Placement", "placement_port", ""),
    ("Heat", "heat_port", "/v1"),
    ("Swift", "swift_port", "/v1"),
    ("Barbican", "barbican_port", "/v1"),
    ("Octavia", "octavia_port", "/v2"),
    ("Admin", "admin_port", ""),
]


@click.group()
@click.version_option(version=_VERSION)
def cli():
    """LocalOStack - Local OpenStack API Emulator"""
    pass


@cli.command()
def start():
    """Start all LocalOStack services."""
    from localostack.core.fault_injection import FaultRegistry, FaultRule
    from localostack.core.gateway import MultiPortServer
    from localostack.core.persistence import create_backend
    from localostack.providers.keystone.app import create_keystone_app
    from localostack.providers.nova.app import create_nova_app
    from localostack.providers.neutron.app import create_neutron_app
    from localostack.providers.glance.app import create_glance_app
    from localostack.providers.cinder.app import create_cinder_app
    from localostack.providers.placement.app import create_placement_app
    from localostack.providers.heat.app import create_heat_app
    from localostack.providers.swift.app import create_swift_app
    from localostack.providers.barbican.app import create_barbican_app
    from localostack.providers.octavia.app import create_octavia_app
    from localostack.admin.app import create_admin_app

    config = load_config()

    # Print startup banner
    click.echo()
    click.echo(f" LocalOStack v{_VERSION}")
    click.echo(" " + "\u2500" * 41)
    dash9 = "\u2500" * 9
    dash4 = "\u2500" * 4
    dash8 = "\u2500" * 8
    click.echo(f"  {'Service':<13}{'Port':<7}Endpoint")
    click.echo(f"  {dash9:<13}{dash4:<7}{dash8}")
    for name, port_attr, version_path in _SERVICES:
        port = getattr(config, port_attr)
        endpoint = f"http://{config.host}:{port}{version_path}"
        click.echo(f"  {name:<13}{port:<7}{endpoint}")
    click.echo(" " + "\u2500" * 41)
    if config.persistence != "memory":
        click.echo(f"  Persistence: {config.persistence} ({config.db_path})")
    click.echo()

    registry = FaultRegistry()
    if config.fault_rules_json:
        try:
            rules_data = json.loads(config.fault_rules_json)
            if isinstance(rules_data, list):
                for r in rules_data:
                    registry.add_rule(FaultRule(**r))
            logger.info(f"  Loaded {len(registry.get_rules())} fault rules from env")
        except Exception as e:
            logger.warning(f"  Failed to load fault rules: {e}")

    backend = create_backend(config.persistence, config.db_path)

    keystone_app = create_keystone_app(backend=backend, fault_registry=registry)
    admin_proj = keystone_app.state.keystone_store.find_project_by_name(
        config.admin_project, config.default_domain,
    )
    admin_project_id = admin_proj.id if admin_proj else config.admin_project

    # Collect service apps for reset support
    service_apps = [keystone_app]

    nova_app = create_nova_app(backend=backend, fault_registry=registry)
    neutron_app = create_neutron_app(admin_project_id=admin_project_id, backend=backend, fault_registry=registry)
    glance_app = create_glance_app(admin_project_id=admin_project_id, backend=backend, fault_registry=registry)
    cinder_app = create_cinder_app(backend=backend, fault_registry=registry)
    placement_app = create_placement_app(backend=backend, fault_registry=registry)
    heat_app = create_heat_app(backend=backend, fault_registry=registry)
    swift_app = create_swift_app(backend=backend, fault_registry=registry)
    barbican_app = create_barbican_app(backend=backend, fault_registry=registry)
    octavia_app = create_octavia_app(backend=backend, fault_registry=registry)

    service_apps.extend([
        nova_app, neutron_app, glance_app, cinder_app,
        placement_app, heat_app, swift_app, barbican_app, octavia_app,
    ])

    admin_app = create_admin_app(registry, config=config, service_apps=service_apps)

    server = MultiPortServer()
    server.add(keystone_app, config.host, config.keystone_port, "keystone")
    server.add(nova_app, config.host, config.nova_port, "nova")
    server.add(neutron_app, config.host, config.neutron_port, "neutron")
    server.add(glance_app, config.host, config.glance_port, "glance")
    server.add(cinder_app, config.host, config.cinder_port, "cinder")
    server.add(placement_app, config.host, config.placement_port, "placement")
    server.add(heat_app, config.host, config.heat_port, "heat")
    server.add(swift_app, config.host, config.swift_port, "swift")
    server.add(barbican_app, config.host, config.barbican_port, "barbican")
    server.add(octavia_app, config.host, config.octavia_port, "octavia")
    server.add(admin_app, config.host, config.admin_port, "admin")

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("LocalOStack stopped.")
        sys.exit(0)


@cli.command()
def status():
    """Show status of LocalOStack services."""
    import httpx

    config = load_config()

    def _check(name: str, port: int) -> tuple[str, int, str, str]:
        url = f"http://localhost:{port}/"
        try:
            resp = httpx.get(url, timeout=2.0)
            elapsed = resp.elapsed.total_seconds() * 1000
            return (name, port, "UP", f"{elapsed:.0f}ms")
        except httpx.ConnectError:
            return (name, port, "DOWN", "-")
        except Exception:
            return (name, port, "DOWN", "-")

    services = [(name, getattr(config, port_attr)) for name, port_attr, _ in _SERVICES]

    results = []
    with ThreadPoolExecutor(max_workers=len(services)) as executor:
        futures = {executor.submit(_check, name, port): name for name, port in services}
        for future in as_completed(futures):
            results.append(future.result())

    # Sort by original order
    order = {name: i for i, (name, _) in enumerate(services)}
    results.sort(key=lambda r: order[r[0]])

    all_down = all(status == "DOWN" for _, _, status, _ in results)
    if all_down:
        click.echo("LocalOStack is not running.")
        sys.exit(1)

    click.echo()
    dash9 = "\u2500" * 9
    dash4 = "\u2500" * 4
    dash6 = "\u2500" * 6
    dash8 = "\u2500" * 8
    click.echo(f"  {'Service':<13}{'Port':<7}{'Status':<8}{'Response'}")
    click.echo(f"  {dash9:<13}{dash4:<7}{dash6:<8}{dash8}")
    for name, port, status, elapsed in results:
        status_colored = click.style(status, fg="green" if status == "UP" else "red")
        click.echo(f"  {name:<13}{port:<7}{status_colored:<17}{elapsed}")
    click.echo()


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing clouds.yaml")
def init(force):
    """Generate clouds.yaml for LocalOStack."""
    clouds_dir = Path.home() / ".config" / "openstack"
    clouds_file = clouds_dir / "clouds.yaml"

    if clouds_file.exists() and not force:
        click.echo(f"Error: {clouds_file} already exists. Use --force to overwrite.", err=True)
        sys.exit(1)

    clouds_dir.mkdir(parents=True, exist_ok=True)

    content = """\
clouds:
  localostack:
    auth:
      auth_url: http://localhost:5000/v3
      project_name: admin
      username: admin
      password: password
      user_domain_name: Default
      project_domain_name: Default
    region_name: RegionOne
    interface: public
    identity_api_version: 3
"""
    clouds_file.write_text(content)
    click.echo(f"Generated {clouds_file}")


@cli.command()
def reset():
    """Reset all in-memory state (requires running server)."""
    import httpx

    config = load_config()
    url = f"http://localhost:{config.admin_port}/reset"
    try:
        resp = httpx.post(url, timeout=5.0)
        if resp.status_code == 200:
            click.echo("All services reset successfully.")
        else:
            click.echo(f"Reset failed: {resp.status_code} {resp.text}", err=True)
            sys.exit(1)
    except httpx.ConnectError:
        click.echo("LocalOStack is not running.")
        sys.exit(1)


if __name__ == "__main__":
    cli()
