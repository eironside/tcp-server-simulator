"""Asyncio UDP server that consumes datagrams as framed records.

Each datagram is one record (FR-58 / FR-60 second clause). Oversized
datagrams (> max_record_bytes) are truncated and flagged. Optional
multicast-group join lets the receiver tap RATs that publish via multicast.
"""

from __future__ import annotations

import asyncio
import socket
import struct
from dataclasses import dataclass
from typing import Callable, Optional

from tcp_sim.engine.framer import FramedRecord

from .base import EventCallback, EventEmitter

RecordCallback = Callable[[str, FramedRecord], None]


@dataclass(frozen=True)
class UdpServerReceiverConfig:
    host: str = "0.0.0.0"
    port: int = 5565
    max_record_bytes: int = 65535  # max UDP payload anyway
    multicast_group: Optional[str] = None  # e.g. "239.255.0.1"
    multicast_interface: str = "0.0.0.0"


class _ReceiverProtocol(asyncio.DatagramProtocol):
    def __init__(self, receiver: "UdpServerReceiver") -> None:
        self._receiver = receiver

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self._receiver._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:  # pragma: no cover - OS path
        self._receiver._emit_event("udp_error", error=repr(exc))


class UdpServerReceiver(EventEmitter):
    """Bind a UDP port and consume datagrams as records."""

    def __init__(
        self,
        config: UdpServerReceiverConfig | None = None,
        *,
        on_record: RecordCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config or UdpServerReceiverConfig()
        self._init_events(on_event)
        self._on_record = on_record
        self._transport: asyncio.DatagramTransport | None = None
        self._running = False
        self._bound_port = self.config.port

        self.records_received = 0
        self.bytes_received = 0
        self.truncations = 0
        self.record_drops = 0  # engine bumps this on sink overload

    @property
    def bound_port(self) -> int:
        return self._bound_port

    async def start(self) -> None:
        if self._running:
            return
        loop = asyncio.get_running_loop()
        # For multicast we must build the socket ourselves so we can set
        # SO_REUSEADDR and IP_ADD_MEMBERSHIP before binding.
        sock: Optional[socket.socket] = None
        if self.config.multicast_group:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.config.host, self.config.port))
            mreq = struct.pack(
                "4s4s",
                socket.inet_aton(self.config.multicast_group),
                socket.inet_aton(self.config.multicast_interface),
            )
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _ReceiverProtocol(self), sock=sock
            )
        else:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _ReceiverProtocol(self),
                local_addr=(self.config.host, self.config.port),
            )
        self._transport = transport
        self._running = True
        sockname = transport.get_extra_info("sockname")
        if sockname:
            self._bound_port = int(sockname[1])
        self._emit_event(
            "receiver_listening",
            host=self.config.host,
            port=self._bound_port,
            multicast=self.config.multicast_group,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        self._emit_event("receiver_stopped")

    # UDP cannot pause cleanly; sink backpressure drops at submit instead.
    def set_paused(self, paused: bool) -> None:  # noqa: D401 - interface parity
        """No-op: UDP uses drop-on-full instead of pause."""
        return

    def _on_datagram(self, data: bytes, addr: tuple[str, int]) -> None:
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
