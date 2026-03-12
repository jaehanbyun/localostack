import asyncio
import signal
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI

logger = logging.getLogger(__name__)


class MultiPortServer:
    """여러 포트에서 서로 다른 FastAPI 앱을 서빙하는 단일 프로세스 서버"""

    def __init__(self):
        self._servers: list[uvicorn.Server] = []
        self._service_map: dict[int, str] = {}

    def add(self, app: FastAPI, host: str, port: int, service_name: str = "", **kwargs):
        config = uvicorn.Config(
            app=app,
            host=host,
            port=port,
            log_level="info",
            **kwargs,
        )
        server = uvicorn.Server(config)
        self._servers.append(server)
        self._service_map[port] = service_name or f"service-{port}"

    async def serve(self):
        loop = asyncio.get_running_loop()

        def _signal_handler():
            logger.info("Shutting down all services...")
            for server in self._servers:
                server.should_exit = True

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _signal_handler)

        for port, name in self._service_map.items():
            logger.info(f"Starting {name} on port {port}")

        await asyncio.gather(*(server.serve() for server in self._servers))

    def run(self):
        asyncio.run(self.serve())
