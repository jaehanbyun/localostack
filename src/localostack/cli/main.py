import json
import logging
import sys

from localostack.core.config import load_config
from localostack.core.fault_injection import FaultRegistry, FaultRule
from localostack.core.gateway import MultiPortServer
from localostack.core.persistence import create_backend
from localostack.providers.keystone.app import create_keystone_app
from localostack.providers.nova.app import create_nova_app
from localostack.providers.neutron.app import create_neutron_app
from localostack.providers.glance.app import create_glance_app
from localostack.providers.cinder.app import create_cinder_app
from localostack.providers.placement.app import create_placement_app
from localostack.admin.app import create_admin_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("localostack")


def main():
    config = load_config()

    logger.info("Starting LocalOStack...")
    logger.info(f"  Keystone: {config.host}:{config.keystone_port}")
    logger.info(f"  Nova:     {config.host}:{config.nova_port}")
    logger.info(f"  Neutron:  {config.host}:{config.neutron_port}")
    logger.info(f"  Glance:   {config.host}:{config.glance_port}")
    logger.info(f"  Cinder:   {config.host}:{config.cinder_port}")
    logger.info(f"  Placement: {config.host}:{config.placement_port}")
    logger.info(f"  Admin:    {config.host}:{config.admin_port}")
    if config.persistence != "memory":
        logger.info(f"  Persistence: {config.persistence} ({config.db_path})")

    registry = FaultRegistry()
    # Load initial fault rules from env var if set
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

    server = MultiPortServer()
    server.add(keystone_app, config.host, config.keystone_port, "keystone")
    server.add(create_nova_app(backend=backend, fault_registry=registry), config.host, config.nova_port, "nova")
    server.add(create_neutron_app(admin_project_id=admin_project_id, backend=backend, fault_registry=registry), config.host, config.neutron_port, "neutron")
    server.add(create_glance_app(admin_project_id=admin_project_id, backend=backend, fault_registry=registry), config.host, config.glance_port, "glance")
    server.add(create_cinder_app(backend=backend, fault_registry=registry), config.host, config.cinder_port, "cinder")
    server.add(create_placement_app(backend=backend, fault_registry=registry), config.host, config.placement_port, "placement")
    server.add(create_admin_app(registry), config.host, config.admin_port, "admin")

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("LocalOStack stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
