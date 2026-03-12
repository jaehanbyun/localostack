import logging
import sys

from localostack.core.config import load_config
from localostack.core.gateway import MultiPortServer
from localostack.providers.keystone.app import create_keystone_app
from localostack.providers.nova.app import create_nova_app
from localostack.providers.neutron.app import create_neutron_app
from localostack.providers.glance.app import create_glance_app
from localostack.providers.cinder.app import create_cinder_app

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

    keystone_app = create_keystone_app()
    admin_proj = keystone_app.state.keystone_store.find_project_by_name(
        config.admin_project, config.default_domain,
    )
    admin_project_id = admin_proj.id if admin_proj else config.admin_project

    server = MultiPortServer()
    server.add(keystone_app, config.host, config.keystone_port, "keystone")
    server.add(create_nova_app(), config.host, config.nova_port, "nova")
    server.add(create_neutron_app(admin_project_id=admin_project_id), config.host, config.neutron_port, "neutron")
    server.add(create_glance_app(admin_project_id=admin_project_id), config.host, config.glance_port, "glance")
    server.add(create_cinder_app(), config.host, config.cinder_port, "cinder")

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("LocalOStack stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
