"""Asyncio UDP server with multicast or reply-to-senders modes."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass

from .base import EventCallback, EventEmitter


@dataclass(frozen=True)
class UdpServerConfig:
    host: str = "0.0.0.0"
    port: int = 5565
    recipient_mode: str = "reply_to_senders"
    multicast_host: str = "239.255.0.1"
    multicast_port: int = 5565
    recipient_cache_ttl_seconds: float = 300.0
    recipient_cache_max_entries: int = 256
    recipient_cache_cleanup_interval_seconds: float = 30.0


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, server: "UdpServerSender") -> None:
        self._server = server

    def datagram_received(self, _data: bytes, addr: tuple[str, int]) -> None:
        self._server.register_sender(addr)


class UdpServerSender(EventEmitter):
    """UDP listener/sender with recipient cache management."""

    def __init__(
        self,
        config: UdpServerConfig | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config or UdpServerConfig()
        self._init_events(on_event)

        self._transport: asyncio.DatagramTransport | None = None
        self._protocol: _UdpProtocol | None = None
        self._cleanup_task: asyncio.Task[None] | None = None
        self._recipient_cache: OrderedDict[tuple[str, int], float] = OrderedDict()
        self._running = False
        self._bound_port = self.config.port

    @property
    def bound_port(self) -> int:
        return self._bound_port

    @property
    def recipient_count(self) -> int:
        return len(self._recipient_cache)

    async def start(self) -> None:
        if self._running:
            return

        loop = asyncio.get_running_loop()
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: _UdpProtocol(self),
            local_addr=(self.config.host, self.config.port),
        )
        self._transport = transport
        self._protocol = protocol
        self._running = True

        socket_info = transport.get_extra_info("sockname")
        if socket_info:
            self._bound_port = int(socket_info[1])

        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._emit_event("udp_server_started", port=self._bound_port)

    async def stop(self) -> None:
        if not self._running:
            return

        self._running = False
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            await asyncio.gather(self._cleanup_task, return_exceptions=True)
            self._cleanup_task = None

        if self._transport is not None:
            self._transport.close()
            self._transport = None

        self._recipient_cache.clear()
        self._emit_event("udp_server_stopped")

    async def send(self, payload: bytes) -> None:
        if self._transport is None:
            raise RuntimeError("UDP server is not started")

        self.cleanup_expired()
        if self.config.recipient_mode == "multicast":
            self._transport.sendto(
                payload, (self.config.multicast_host, self.config.multicast_port)
            )
            self._emit_event("udp_send_multicast", bytes=len(payload))
            await asyncio.sleep(0)
            return

        for recipient in self._recipient_cache.keys():
            self._transport.sendto(payload, recipient)

        self._emit_event(
            "udp_send_reply", recipients=len(self._recipient_cache), bytes=len(payload)
        )
        await asyncio.sleep(0)

    def register_sender(self, addr: tuple[str, int]) -> None:
        now = time.monotonic()
        if addr in self._recipient_cache:
            self._recipient_cache.move_to_end(addr)
        self._recipient_cache[addr] = now

        while len(self._recipient_cache) > self.config.recipient_cache_max_entries:
            self._recipient_cache.popitem(last=False)
            self._emit_event("udp_recipient_evicted", policy="lru")

    def cleanup_expired(self) -> None:
        now = time.monotonic()
        expired: list[tuple[str, int]] = []

        for recipient, last_seen in self._recipient_cache.items():
            if now - last_seen > self.config.recipient_cache_ttl_seconds:
                expired.append(recipient)

        for recipient in expired:
            self._recipient_cache.pop(recipient, None)

        if expired:
            self._emit_event("udp_recipient_expired", count=len(expired))

    async def _cleanup_loop(self) -> None:
        while self._running:
            self.cleanup_expired()
            await asyncio.sleep(self.config.recipient_cache_cleanup_interval_seconds)
