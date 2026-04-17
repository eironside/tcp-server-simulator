"""Asyncio TCP client with reconnect behavior."""

from __future__ import annotations

import asyncio
import ssl
from contextlib import suppress
from dataclasses import dataclass

from .base import EventCallback, EventEmitter, ReconnectBackoff


@dataclass(frozen=True)
class TcpClientConfig:
    host: str
    port: int
    connect_timeout_seconds: float = 10.0
    send_timeout_seconds: float = 10.0
    reconnect_max_backoff_seconds: float = 30.0
    use_tls: bool = False
    tls_ca_file: str | None = None
    tls_verify: bool = True
    tls_server_hostname: str | None = None


def create_client_ssl_context(config: TcpClientConfig) -> ssl.SSLContext | None:
    if not config.use_tls:
        return None

    if not config.tls_verify:
        raise ValueError("Insecure TLS mode is not supported; enable tls_verify")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_default_certs(ssl.Purpose.SERVER_AUTH)

    if config.tls_ca_file:
        context.load_verify_locations(config.tls_ca_file)

    return context


class TcpClientSender(EventEmitter):
    """TCP client that reconnects automatically when disconnected."""

    def __init__(
        self,
        config: TcpClientConfig,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self._init_events(on_event)

        self._running = False
        self._run_task: asyncio.Task[None] | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._outbound: asyncio.Queue[bytes] = asyncio.Queue()

        self.reconnect_count = 0
        self.last_disconnect_reason = ""
        self.connected_event = asyncio.Event()

    async def start(self) -> None:
        if self._running:
            return

        self._running = True
        self._run_task = asyncio.create_task(self._run())
        await asyncio.sleep(0)

    async def stop(self) -> None:
        self._running = False

        if self._run_task is not None:
            self._run_task.cancel()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    asyncio.gather(self._run_task, return_exceptions=True),
                    timeout=2.0,
                )
            self._run_task = None

        await self._close_connection(reason="client_stop")

    async def send(self, payload: bytes) -> None:
        await self._outbound.put(payload)

    async def _run(self) -> None:
        backoff = ReconnectBackoff(
            initial_seconds=1.0,
            max_seconds=self.config.reconnect_max_backoff_seconds,
        )
        ssl_context = create_client_ssl_context(self.config)
        tls_server_hostname = (
            self.config.tls_server_hostname
            if self.config.tls_server_hostname
            else self.config.host
        )

        while self._running:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        self.config.host,
                        self.config.port,
                        ssl=ssl_context,
                        server_hostname=(
                            tls_server_hostname if ssl_context is not None else None
                        ),
                    ),
                    timeout=self.config.connect_timeout_seconds,
                )
                self.connected_event.set()
                self._emit_event(
                    "client_connect", host=self.config.host, port=self.config.port
                )
                backoff.reset()

                await self._connected_loop()
            except OSError as exc:
                self.last_disconnect_reason = str(exc)
                self._emit_event(
                    "client_reconnect_pending",
                    reason=str(exc),
                    backoff=backoff.current,
                )
            finally:
                await self._close_connection(
                    reason=self.last_disconnect_reason or "disconnect"
                )

            if not self._running:
                break

            self.reconnect_count += 1
            delay = backoff.advance()
            await asyncio.sleep(delay)

    async def _connected_loop(self) -> None:
        assert self._reader is not None
        assert self._writer is not None

        disconnect_watch = asyncio.create_task(self._reader.read(1))

        try:
            while self._running:
                if disconnect_watch.done():
                    data = disconnect_watch.result()
                    if data == b"":
                        raise ConnectionError("Remote server disconnected")
                    disconnect_watch = asyncio.create_task(self._reader.read(1))

                try:
                    payload = await asyncio.wait_for(self._outbound.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    continue

                self._writer.write(payload)
                await asyncio.wait_for(
                    self._writer.drain(),
                    timeout=self.config.send_timeout_seconds,
                )
                self._emit_event("client_send", bytes=len(payload))
        finally:
            disconnect_watch.cancel()
            await asyncio.gather(disconnect_watch, return_exceptions=True)

    async def _close_connection(self, reason: str) -> None:
        if self._writer is not None:
            with suppress(OSError, RuntimeError, asyncio.TimeoutError):
                self._writer.close()
                await asyncio.wait_for(self._writer.wait_closed(), timeout=1.0)

        self._writer = None
        self._reader = None
        self.connected_event.clear()
        if reason:
            self.last_disconnect_reason = reason
            self._emit_event("client_disconnect", reason=reason)
