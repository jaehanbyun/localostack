import logging
import sys

from localostack.core.config import load_config
from localostack.core.gateway import MultiPortServer
from localostack.providers.keystone.app import create_keystone_app
from localostack.providers.nova.app import create_nova_app
from localostack.providers.neutron.app import create_neutron_app
from localostack.providers.glance.app import create_glance_app

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

    server = MultiPortServer()
    server.add(create_keystone_app(), config.host, config.keystone_port, "keystone")
    server.add(create_nova_app(), config.host, config.nova_port, "nova")
    server.add(create_neutron_app(), config.host, config.neutron_port, "neutron")
    server.add(create_glance_app(), config.host, config.glance_port, "glance")

    try:
        server.run()
    except KeyboardInterrupt:
        logger.info("LocalOStack stopped.")
        sys.exit(0)


if __name__ == "__main__":
    main()
