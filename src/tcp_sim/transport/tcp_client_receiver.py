"""Asyncio TCP client that consumes framed records from a remote server."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from typing import Callable, Optional

from tcp_sim.engine.framer import FramedRecord, Framer, FramingMode

from .base import EventCallback, EventEmitter, ReconnectBackoff
from .tcp_client_sender import TcpClientConfig, create_client_ssl_context

RecordCallback = Callable[[str, FramedRecord], None]


@dataclass(frozen=True)
class TcpClientReceiverConfig:
    host: str
    port: int
    connect_timeout_seconds: float = 10.0
    reconnect_max_backoff_seconds: float = 30.0
    framing_mode: FramingMode = FramingMode.LF
    max_record_bytes: int = 1 << 20
    read_chunk_bytes: int = 65536
    use_tls: bool = False
    tls_ca_file: Optional[str] = None
    tls_verify: bool = True
    tls_server_hostname: Optional[str] = None

    def _as_client_sender_config(self) -> TcpClientConfig:
        return TcpClientConfig(
            host=self.host,
            port=self.port,
            connect_timeout_seconds=self.connect_timeout_seconds,
            reconnect_max_backoff_seconds=self.reconnect_max_backoff_seconds,
            use_tls=self.use_tls,
            tls_ca_file=self.tls_ca_file,
            tls_verify=self.tls_verify,
            tls_server_hostname=self.tls_server_hostname,
        )


class TcpClientReceiver(EventEmitter):
    """Connect outbound to a TCP server and read framed records.

    Auto-reconnects with exponential backoff (shared policy with the sender
    client via :class:`ReconnectBackoff`).
    """

    def __init__(
        self,
        config: TcpClientReceiverConfig,
        *,
        on_record: RecordCallback | None = None,
        on_event: EventCallback | None = None,
    ) -> None:
        self.config = config
        self._init_events(on_event)
        self._on_record = on_record

        self._running = False
        self._run_task: asyncio.Task[None] | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._paused = asyncio.Event()
        self._paused.set()

        self.reconnect_count = 0
        self.records_received = 0
        self.bytes_received = 0
        self.truncations = 0
        self.connected_event = asyncio.Event()

    # ----- Lifecycle -------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._run_task = asyncio.create_task(self._run(), name="tcp-client-receiver")
        await asyncio.sleep(0)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._run_task is not None:
            self._run_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._run_task
            self._run_task = None
        self._close_writer()
        self._emit_event("receiver_stopped")

    def set_paused(self, paused: bool) -> None:
        if paused:
            if self._paused.is_set():
                self._paused.clear()
                self._emit_event("receiver_paused")
        else:
            if not self._paused.is_set():
                self._paused.set()
                self._emit_event("receiver_resumed")

    # ----- Run loop --------------------------------------------------------

    async def _run(self) -> None:
        backoff = ReconnectBackoff(
            initial_seconds=1.0,
            max_seconds=self.config.reconnect_max_backoff_seconds,
        )
        ssl_ctx = create_client_ssl_context(self.config._as_client_sender_config())
        src = f"{self.config.host}:{self.config.port}"
        while self._running:
            try:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        host=self.config.host,
                        port=self.config.port,
                        ssl=ssl_ctx,
                        server_hostname=(
                            self.config.tls_server_hostname
                            if self.config.use_tls
                            else None
                        ),
                    ),
                    timeout=self.config.connect_timeout_seconds,
                )
            except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
                delay = backoff.advance()
                self._emit_event(
                    "reconnect_pending",
                    reason=f"connect_error:{exc.__class__.__name__}",
                    delay_seconds=delay,
                )
                try:
                    await asyncio.sleep(delay)
                except asyncio.CancelledError:
                    raise
                continue

            backoff.reset()
            self.connected_event.set()
            self._emit_event("receiver_connected", src=src)
            framer = Framer(
                mode=self.config.framing_mode,
                max_record_bytes=self.config.max_record_bytes,
            )
            reason = "eof"
            try:
                while self._running:
                    if not self._paused.is_set():
                        await self._paused.wait()
                    try:
                        chunk = await self._reader.read(self.config.read_chunk_bytes)
                    except (ConnectionError, OSError) as exc:
                        reason = f"error:{exc.__class__.__name__}"
                        break
                    if not chunk:
                        break
                    self.bytes_received += len(chunk)
                    for record in framer.feed(chunk):
                        self._deliver(src, record)
                trailing = framer.flush()
                if trailing is not None:
                    self._deliver(src, trailing)
            finally:
                self.connected_event.clear()
                self._close_writer()
                self._emit_event("receiver_disconnected", src=src, reason=reason)

            if not self._running:
                break
            self.reconnect_count += 1
            delay = backoff.advance()
            self._emit_event(
                "reconnect_pending",
                reason=reason,
                delay_seconds=delay,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

    def _close_writer(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self._reader = None

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
