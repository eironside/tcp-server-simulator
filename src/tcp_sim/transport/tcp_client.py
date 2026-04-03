"""Asyncio TCP client with reconnect behavior."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable


EventCallback = Callable[[dict[str, object]], None]


@dataclass(frozen=True)
class TcpClientConfig:
    host: str
    port: int
    connect_timeout_seconds: float = 10.0
    send_timeout_seconds: float = 10.0
    reconnect_max_backoff_seconds: float = 30.0


class TcpClient:
    """TCP client that reconnects automatically when disconnected."""

    def __init__(
        self,
        config: TcpClientConfig,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self._on_event = on_event

        self._running = False
        self._run_task: asyncio.Task[None] | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader: asyncio.StreamReader | None = None
        self._outbound: asyncio.Queue[bytes] = asyncio.Queue()

        self.events: list[dict[str, object]] = []
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
        backoff = 1.0

        while self._running:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.config.host, self.config.port),
                    timeout=self.config.connect_timeout_seconds,
                )
                self.connected_event.set()
                self._emit_event("client_connect", host=self.config.host, port=self.config.port)
                backoff = 1.0

                await self._connected_loop()
            except OSError as exc:
                self.last_disconnect_reason = str(exc)
                self._emit_event("client_reconnect_pending", reason=str(exc), backoff=backoff)
            finally:
                await self._close_connection(reason=self.last_disconnect_reason or "disconnect")

            if not self._running:
                break

            self.reconnect_count += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self.config.reconnect_max_backoff_seconds)

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

    def _emit_event(self, event: str, **payload: object) -> None:
        record = {"event": event, **payload}
        self.events.append(record)
        if self._on_event is not None:
            self._on_event(record)
