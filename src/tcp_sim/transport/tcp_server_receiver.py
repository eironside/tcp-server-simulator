"""Asyncio TCP server that consumes framed records from connected peers."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Optional

from tcp_sim.engine.framer import FramedRecord, Framer, FramingMode

from .base import EventCallback, EventEmitter
from .tcp_server_sender import TcpServerConfig, create_server_ssl_context

RecordCallback = Callable[[str, FramedRecord], None]


@dataclass(frozen=True)
class TcpServerReceiverConfig:
    host: str = "0.0.0.0"
    port: int = 5565
    framing_mode: FramingMode = FramingMode.LF
    max_record_bytes: int = 1 << 20
    # Read buffer per peer; small enough to react to pause requests quickly.
    read_chunk_bytes: int = 65536
    use_tls: bool = False
    tls_certfile: Optional[str] = None
    tls_keyfile: Optional[str] = None
    tls_ca_file: Optional[str] = None
    tls_require_client_cert: bool = False

    def _as_server_sender_config(self) -> TcpServerConfig:
        # Reuse the sender's SSL context factory (identical requirements).
        return TcpServerConfig(
            host=self.host,
            port=self.port,
            use_tls=self.use_tls,
            tls_certfile=self.tls_certfile,
            tls_keyfile=self.tls_keyfile,
            tls_ca_file=self.tls_ca_file,
            tls_require_client_cert=self.tls_require_client_cert,
        )


class TcpServerReceiver(EventEmitter):
    """Accept inbound TCP peers and read framed records from each concurrently.

    Records are delivered via `on_record(src, FramedRecord)`. Lifecycle events
    are emitted via `on_event` (see EventEmitter).

    Per-peer read pause: call :meth:`set_paused(True)` to stop reading from
    every peer until :meth:`set_paused(False)`. This is how the receiver
    engine propagates sink backpressure to TCP peers.
    """

    def __init__(
        self,
        config: TcpServerReceiverConfig | None = None,
        *,
        on_record: RecordCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config or TcpServerReceiverConfig()
        self._init_events(on_event)
        self._on_record = on_record

        self._server: asyncio.AbstractServer | None = None
        self._peer_tasks: dict[str, asyncio.Task[None]] = {}
        self._running = False
        self._paused = asyncio.Event()
        self._paused.set()  # Set = "not paused" (readers may proceed)

        self.records_received = 0
        self.bytes_received = 0
        self.truncations = 0

    # ----- Lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        ssl_ctx = create_server_ssl_context(self.config._as_server_sender_config())
        self._server = await asyncio.start_server(
            self._handle_peer,
            host=self.config.host,
            port=self.config.port,
            ssl=ssl_ctx,
        )
        self._running = True
        sockets = self._server.sockets or []
        bound_port = sockets[0].getsockname()[1] if sockets else self.config.port
        self._emit_event(
            "receiver_listening",
            host=self.config.host,
            port=bound_port,
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._server is not None:
            self._server.close()
            with suppress(Exception):
                await self._server.wait_closed()
            self._server = None
        peer_tasks = list(self._peer_tasks.values())
        for task in peer_tasks:
            task.cancel()
        if peer_tasks:
            # Bound the wait: a peer that refuses to close its side of the
            # socket must not be able to hang the whole shutdown path.
            try:
                await asyncio.wait_for(
                    asyncio.gather(*peer_tasks, return_exceptions=True),
                    timeout=2.0,
                )
            except asyncio.TimeoutError:
                self._emit_event(
                    "receiver_stop_timeout",
                    stuck_peer_count=sum(1 for t in peer_tasks if not t.done()),
                )
        self._peer_tasks.clear()
        self._emit_event("receiver_stopped")

    # ----- Backpressure ----------------------------------------------------

    def set_paused(self, paused: bool) -> None:
        """Pause or resume reads from every connected peer."""
        if paused:
            if self._paused.is_set():
                self._paused.clear()
                self._emit_event("receiver_paused")
        else:
            if not self._paused.is_set():
                self._paused.set()
                self._emit_event("receiver_resumed")

    @property
    def peer_count(self) -> int:
        return len(self._peer_tasks)

    # ----- Peer handler ----------------------------------------------------

    async def _handle_peer(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        src = _format_peer(peer)
        task = asyncio.current_task()
        if task is not None:
            self._peer_tasks[src] = task
        self._emit_event("peer_connected", src=src)
        framer = Framer(
            mode=self.config.framing_mode,
            max_record_bytes=self.config.max_record_bytes,
        )
        reason = "eof"
        try:
            while self._running:
                if not self._paused.is_set():
                    # Block until the engine clears backpressure.
                    await self._paused.wait()
                try:
                    chunk = await reader.read(self.config.read_chunk_bytes)
                except (ConnectionError, OSError) as exc:
                    reason = f"error:{exc.__class__.__name__}"
                    break
                if not chunk:
                    break
                self.bytes_received += len(chunk)
                for record in framer.feed(chunk):
                    self._deliver(src, record)
            # Flush any trailing unterminated record on clean EOF.
            trailing = framer.flush()
            if trailing is not None:
                self._deliver(src, trailing)
        except asyncio.CancelledError:
            reason = "cancelled"
            raise
        finally:
            self._peer_tasks.pop(src, None)
            writer.close()
            with suppress(OSError, RuntimeError, asyncio.TimeoutError):
                # Bound wait_closed() so a half-closed remote cannot wedge
                # the stop path.
                await asyncio.wait_for(writer.wait_closed(), timeout=1.0)
            self._emit_event("peer_disconnected", src=src, reason=reason)

    def _deliver(self, src: str, record: FramedRecord) -> None:
        self.records_received += 1
        if record.truncated:
            self.truncations += 1
            self._emit_event(
                "record_truncated",
                src=src,
                bytes_len=len(record.payload),
            )
        if self._on_record is not None:
            self._on_record(src, record)


def _format_peer(peer: object) -> str:
    if isinstance(peer, tuple) and len(peer) >= 2:
        return f"{peer[0]}:{peer[1]}"
    return str(peer)
