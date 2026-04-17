"""Asyncio UDP client receiver.

Binds an ephemeral local port, optionally sends a configurable "hello"
datagram to the remote host:port so that publishers using reply-to-senders
semantics know where to ship data, and consumes datagrams from any source
(or filtered to the configured remote peer).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Callable, Optional

from tcp_sim.engine.framer import FramedRecord

from .base import EventCallback, EventEmitter

RecordCallback = Callable[[str, FramedRecord], None]


@dataclass(frozen=True)
class UdpClientReceiverConfig:
    host: str
    port: int
    local_host: str = "0.0.0.0"
    local_port: int = 0
    max_record_bytes: int = 65535
    hello_payload: Optional[bytes] = None
    hello_interval_seconds: float = 0.0  # 0 = send only once at start
    # When True, datagrams from sources other than (host, port) are dropped.
    filter_remote_peer: bool = False


class _ReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, receiver: "UdpClientReceiver") -> None:
        self._receiver = receiver

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._receiver._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover
        self._receiver._emit_event("udp_error", error=repr(exc))


class UdpClientReceiver(EventEmitter):
    def __init__(
        self,
        config: UdpClientReceiverConfig,
        *,
        on_record: RecordCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self._init_events(on_event)
        self._on_record = on_record
        self._transport: asyncio.DatagramTransport | None = None
        self._hello_task: asyncio.Task[None] | None = None
        self._running = False

        self.records_received = 0
        self.bytes_received = 0
        self.truncations = 0
        self.record_drops = 0
        self.packets_filtered = 0

    async def start(self) -> None:
        if self._running:
            return
        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: _ReceiverProtocol(self),
            local_addr=(self.config.local_host, self.config.local_port),
        )
        self._transport = transport
        self._running = True
        sockname = transport.get_extra_info("sockname")
        bound_port = int(sockname[1]) if sockname else self.config.local_port
        self._emit_event(
            "receiver_bound",
            host=self.config.local_host,
            port=bound_port,
            remote=(self.config.host, self.config.port),
        )
        if self.config.hello_payload:
            self._send_hello()
            if self.config.hello_interval_seconds > 0:
                self._hello_task = asyncio.create_task(self._hello_loop())

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._hello_task is not None:
            self._hello_task.cancel()
            try:
                await self._hello_task
            except (asyncio.CancelledError, Exception):
                pass
            self._hello_task = None
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._emit_event("receiver_stopped")

    def set_paused(self, paused: bool) -> None:  # noqa: D401
        """No-op: UDP uses drop-on-full instead of pause."""
        return

    def _send_hello(self) -> None:
        if self._transport is None or not self.config.hello_payload:
            return
        self._transport.sendto(
            self.config.hello_payload, (self.config.host, self.config.port)
        )
        self._emit_event("udp_hello_sent", remote=(self.config.host, self.config.port))

    async def _hello_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.config.hello_interval_seconds)
            except asyncio.CancelledError:
                raise
            if self._running:
                self._send_hello()

    def _on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
        if self.config.filter_remote_peer:
            if addr[0] != self.config.host or addr[1] != self.config.port:
                self.packets_filtered += 1
                return
        src = f"{addr[0]}:{addr[1]}"
        self.bytes_received += len(data)
        self.records_received += 1
        truncated = False
        if len(data) > self.config.max_record_bytes:
            data = data[: self.config.max_record_bytes]
            truncated = True
            self.truncations += 1
            self._emit_event("record_truncated", src=src, bytes_len=len(data))
        record = FramedRecord(payload=data, truncated=truncated)
        if self._on_record is not None:
            self._on_record(src, record)
