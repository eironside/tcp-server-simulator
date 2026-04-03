"""Asyncio TCP server with broadcast and slow-client handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable

from .connection_manager import ConnectionManager, QueueThresholds


EventCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class TcpServerConfig:
    host: str = "0.0.0.0"
    port: int = 5565
    send_timeout_seconds: float = 10.0
    slow_client_timeout_seconds: float = 10.0
    queue_high_watermark_bytes: int = 262144
    queue_low_watermark_bytes: int = 131072
    queue_hard_cap_bytes: int = 524288
    send_header_on_connect: bool = False
    header_payload: bytes | None = None


class TcpServer:
    """TCP server that broadcasts payloads and isolates slow clients."""

    def __init__(
        self,
        config: TcpServerConfig | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config or TcpServerConfig()
        thresholds = QueueThresholds(
            high_watermark_bytes=self.config.queue_high_watermark_bytes,
            low_watermark_bytes=self.config.queue_low_watermark_bytes,
            hard_cap_bytes=self.config.queue_hard_cap_bytes,
            slow_client_timeout_seconds=self.config.slow_client_timeout_seconds,
        )
        self._connection_manager = ConnectionManager(thresholds=thresholds)
        self._on_event = on_event

        self._server: asyncio.AbstractServer | None = None
        self._writer_tasks: dict[str, asyncio.Task[None]] = {}
        self._reader_tasks: dict[str, asyncio.Task[None]] = {}
        self._monitor_task: asyncio.Task[None] | None = None
        self._running = False
        self._listening_port = self.config.port
        self.events: list[dict[str, object]] = []

    @property
    def connected_client_count(self) -> int:
        return self._connection_manager.connected_clients

    @property
    def listening_port(self) -> int:
        return self._listening_port

    def has_clients(self) -> bool:
        return self.connected_client_count > 0

    async def start(self) -> None:
        if self._running:
            return

        self._server = await asyncio.start_server(
            self._on_client_connected,
            host=self.config.host,
            port=self.config.port,
        )
        sockets = self._server.sockets or []
        if sockets:
            self._listening_port = sockets[0].getsockname()[1]

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_slow_clients())
        self._emit_event("server_started", host=self.config.host, port=self._listening_port)

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False

        if self._monitor_task is not None:
            self._monitor_task.cancel()
            await asyncio.gather(self._monitor_task, return_exceptions=True)
            self._monitor_task = None

        for client_id in self._connection_manager.list_client_ids():
            await self._disconnect_client(client_id, reason="server_stop")

        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        self._emit_event("server_stopped")

    async def broadcast(self, payload: bytes) -> None:
        if not payload:
            return

        for client_id in self._connection_manager.list_client_ids():
            accepted, reason = self._connection_manager.enqueue_payload(client_id, payload)
            if not accepted:
                await self._disconnect_client(client_id, reason=reason or "enqueue_failed")

    async def _on_client_connected(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer_name = writer.get_extra_info("peername")
        client_id = str(peer_name)
        self._connection_manager.register_client(client_id, writer)
        self._emit_event("client_connect", client_id=client_id)

        writer_task = asyncio.create_task(self._writer_loop(client_id))
        self._writer_tasks[client_id] = writer_task

        if self.config.send_header_on_connect and self.config.header_payload:
            accepted, reason = self._connection_manager.enqueue_payload(
                client_id, self.config.header_payload
            )
            if not accepted:
                await self._disconnect_client(client_id, reason=reason or "header_enqueue_failed")
                return

        reader_task = asyncio.create_task(self._reader_loop(client_id, reader))
        self._reader_tasks[client_id] = reader_task
        await reader_task

    async def _reader_loop(self, client_id: str, reader: asyncio.StreamReader) -> None:
        try:
            while self._running:
                data = await reader.read(1024)
                if not data:
                    break
        finally:
            await self._disconnect_client(client_id, reason="client_disconnect")

    async def _writer_loop(self, client_id: str) -> None:
        while self._running:
            payload = self._connection_manager.pop_next_payload(client_id)
            if payload is None:
                if self._connection_manager.get_client_state(client_id) is None:
                    return
                await asyncio.sleep(0.01)
                continue

            state = self._connection_manager.get_client_state(client_id)
            if state is None:
                return

            try:
                state.writer.write(payload)
                await asyncio.wait_for(
                    state.writer.drain(),
                    timeout=self.config.send_timeout_seconds,
                )
            except (asyncio.TimeoutError, OSError):
                await self._disconnect_client(client_id, reason="send_failure")
                return

    async def _monitor_slow_clients(self) -> None:
        while self._running:
            for client_id in self._connection_manager.get_disconnect_candidates():
                await self._disconnect_client(client_id, reason="slow_client_timeout")
            await asyncio.sleep(0.05)

    async def _disconnect_client(self, client_id: str, reason: str) -> None:
        state = self._connection_manager.get_client_state(client_id)
        if state is None:
            return

        writer_task = self._writer_tasks.pop(client_id, None)
        if writer_task is not None and writer_task is not asyncio.current_task():
            writer_task.cancel()
            await asyncio.gather(writer_task, return_exceptions=True)

        reader_task = self._reader_tasks.pop(client_id, None)
        if reader_task is not None and reader_task is not asyncio.current_task():
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)

        try:
            state.writer.close()
            await state.writer.wait_closed()
        except (OSError, RuntimeError):
            pass

        self._connection_manager.unregister_client(client_id)
        self._emit_event("client_disconnect", client_id=client_id, reason=reason)

    def _emit_event(self, event: str, **payload: object) -> None:
        record = {"event": event, **payload}
        self.events.append(record)
        if self._on_event is not None:
            self._on_event(record)
