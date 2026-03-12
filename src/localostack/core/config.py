from dataclasses import dataclass, field


@dataclass
class ServiceConfig:
    host: str = "0.0.0.0"
    keystone_port: int = 5000
    nova_port: int = 8774
    neutron_port: int = 9696
    glance_port: int = 9292
    cinder_port: int = 8776

    # Bootstrap
    admin_username: str = "admin"
    admin_password: str = "password"
    admin_project: str = "admin"
    default_domain: str = "default"
    region: str = "RegionOne"

    # Nova 상태 머신
    server_build_mode: str = "sync"  # sync | async | counted
    server_build_delay: int = 5       # async 모드 시 초
    server_build_steps: int = 1       # counted 모드 시 GET 횟수


def load_config() -> ServiceConfig:
    """환경변수에서 설정을 로드한다."""
    import os
    config = ServiceConfig()
    config.host = os.environ.get("LOCALOSTACK_HOST", config.host)
    config.keystone_port = int(os.environ.get("LOCALOSTACK_KEYSTONE_PORT", config.keystone_port))
    config.nova_port = int(os.environ.get("LOCALOSTACK_NOVA_PORT", config.nova_port))
    config.neutron_port = int(os.environ.get("LOCALOSTACK_NEUTRON_PORT", config.neutron_port))
    config.glance_port = int(os.environ.get("LOCALOSTACK_GLANCE_PORT", config.glance_port))
    config.cinder_port = int(os.environ.get("LOCALOSTACK_CINDER_PORT", config.cinder_port))
    config.admin_username = os.environ.get("LOCALOSTACK_ADMIN_USERNAME", config.admin_username)
    config.admin_password = os.environ.get("LOCALOSTACK_ADMIN_PASSWORD", config.admin_password)
    config.server_build_mode = os.environ.get("LOCALOSTACK_SERVER_BUILD_MODE", config.server_build_mode)
    config.server_build_delay = int(os.environ.get("LOCALOSTACK_SERVER_BUILD_DELAY", config.server_build_delay))
    config.server_build_steps = int(os.environ.get("LOCALOSTACK_SERVER_BUILD_STEPS", config.server_build_steps))
    return config
