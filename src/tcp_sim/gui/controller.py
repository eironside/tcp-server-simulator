"""Controller boundary between tkinter UI and async engine/transport."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from queue import Queue
import threading
from typing import Any

from tcp_sim.transport.tcp_client import TcpClient, TcpClientConfig
from tcp_sim.transport.tcp_server import TcpServer, TcpServerConfig
from tcp_sim.transport.udp_client import UdpClient, UdpClientConfig
from tcp_sim.transport.udp_server import UdpServer, UdpServerConfig


@dataclass
class RuntimeSettings:
    mode: str
    protocol: str
    host: str
    port: int
    connect_timeout_seconds: float = 10.0
    send_timeout_seconds: float = 10.0
    reconnect_max_backoff_seconds: float = 30.0


class SimulatorController:
    """Owns async resources and exposes thread-safe control methods for tkinter."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        self._status_queue: Queue[str] = Queue()
        self._active_transport: Any = None
        self._active_settings: RuntimeSettings | None = None

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def read_status_messages(self) -> list[str]:
        messages: list[str] = []
        while not self._status_queue.empty():
            messages.append(self._status_queue.get_nowait())
        return messages

    def _emit(self, message: str) -> None:
        self._status_queue.put(message)

    def apply_settings(self, settings: RuntimeSettings) -> None:
        asyncio.run_coroutine_threadsafe(self._apply_settings_async(settings), self._loop)

    async def _apply_settings_async(self, settings: RuntimeSettings) -> None:
        if self._active_transport is not None:
            self._emit("Applying controlled stop/rebind transition...")
            await self._stop_transport_async()

        self._active_transport = await self._build_transport(settings)
        self._active_settings = settings

        await self._active_transport.start()
        self._emit(f"Transport started: {settings.mode}/{settings.protocol} on {settings.host}:{settings.port}")

    async def _build_transport(self, settings: RuntimeSettings) -> Any:
        mode = settings.mode.lower()
        protocol = settings.protocol.lower()

        if protocol == "tcp" and mode == "server":
            return TcpServer(
                TcpServerConfig(
                    host=settings.host,
                    port=settings.port,
                    send_timeout_seconds=settings.send_timeout_seconds,
                    slow_client_timeout_seconds=settings.send_timeout_seconds,
                )
            )

        if protocol == "tcp" and mode == "client":
            return TcpClient(
                TcpClientConfig(
                    host=settings.host,
                    port=settings.port,
                    connect_timeout_seconds=settings.connect_timeout_seconds,
                    send_timeout_seconds=settings.send_timeout_seconds,
                    reconnect_max_backoff_seconds=settings.reconnect_max_backoff_seconds,
                )
            )

        if protocol == "udp" and mode == "server":
            return UdpServer(
                UdpServerConfig(
                    host=settings.host,
                    port=settings.port,
                )
            )

        if protocol == "udp" and mode == "client":
            return UdpClient(UdpClientConfig(host=settings.host, port=settings.port))

        raise ValueError(f"Unsupported mode/protocol combination: {mode}/{protocol}")

    def stop_transport(self) -> None:
        asyncio.run_coroutine_threadsafe(self._stop_transport_async(), self._loop)

    async def _stop_transport_async(self) -> None:
        if self._active_transport is None:
            return

        await self._active_transport.stop()
        self._emit("Transport stopped.")
        self._active_transport = None

    def shutdown(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self._stop_transport_async(), self._loop)
        future.result(timeout=3)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=3)
