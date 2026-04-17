"""Receiver engine: wires a receiver transport to the sink writer.

Keeps the transport, framer, and sink writer decoupled. This is the engine
surface the GUI controller will talk to for the receiver role; it is the
symmetrical counterpart to :class:`tcp_sim.engine.simulator.SimulatorEngine`
on the sender side.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from tcp_sim.engine.framer import FramedRecord
from tcp_sim.engine.sink_writer import SinkConfig, SinkWriter
from tcp_sim.transport.base import EventCallback


class _TransportLike(Protocol):
    """Structural type covering every receiver transport.

    All receiver transports expose ``start``, ``stop``, ``set_paused``, and
    accept ``on_record`` / ``on_event`` callbacks; this protocol lets the
    engine treat them uniformly.
    """

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def set_paused(self, paused: bool) -> None: ...


@dataclass
class ReceiverStats:
    records_received: int = 0
    bytes_received: int = 0
    truncations: int = 0
    sink_records_written: int = 0
    sink_bytes_written: int = 0
    sink_rotations: int = 0
    sink_records_dropped: int = 0
    sink_backpressured: bool = False
    sink_enabled: bool = False
    sink_path: Optional[str] = None


@dataclass
class _EngineState:
    started: bool = False
    stopping: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)


class ReceiverEngine:
    """Orchestrates a receiver transport + sink writer.

    The caller provides a fully-constructed transport (TCP server/client or
    UDP server/client receiver) and a :class:`SinkConfig`. The engine wires
    records from the transport into the sink and propagates sink backpressure
    to the transport (per-peer TCP read pause, UDP drop-and-count).
    """

    def __init__(
        self,
        transport: _TransportLike,
        sink_config: SinkConfig,
        *,
        on_event: EventCallback | None = None,
    ) -> None:
        self._transport = transport
        self._on_event = on_event
        self._state = _EngineState()
        # Install our own callbacks on the transport (transports expose
        # `_on_record` / `_on_event` via constructor kwargs; we set them
        # directly here for engines that construct transports beforehand).
        setattr(transport, "_on_record", self._handle_record)
        # Chain any existing transport event callback with ours so we don't
        # stomp on callers that pre-wired one for testing.
        prior = getattr(transport, "_on_event", None)

        def _chain(event: dict[str, Any]) -> None:
            if prior is not None:
                prior(event)
            self._handle_transport_event(event)

        setattr(transport, "_on_event", _chain)

        self._sink = SinkWriter(sink_config, on_event=self._handle_sink_event)

    @property
    def stats(self) -> ReceiverStats:
        s = self._sink.stats
        return ReceiverStats(
            records_received=getattr(self._transport, "records_received", 0),
            bytes_received=getattr(self._transport, "bytes_received", 0),
            truncations=getattr(self._transport, "truncations", 0),
            sink_records_written=s.records_written,
            sink_bytes_written=s.bytes_written,
            sink_rotations=s.rotations,
            sink_records_dropped=s.records_dropped,
            sink_backpressured=s.backpressured,
            sink_enabled=s.enabled,
            sink_path=s.current_path,
        )

    async def start(self) -> None:
        if self._state.started:
            return
        await self._sink.start()
        await self._transport.start()
        self._state.started = True
        self._emit("receiver_engine_started")

    async def stop(self) -> None:
        if not self._state.started or self._state.stopping:
            return
        self._state.stopping = True
        try:
            await self._transport.stop()
            await self._sink.stop()
        finally:
            self._state.started = False
            self._state.stopping = False
            self._emit("receiver_engine_stopped")

    async def configure_sink(self, new_config: SinkConfig) -> None:
        await self._sink.configure(new_config)

    # ----- Callbacks -------------------------------------------------------

    def _handle_record(self, src: str, record: FramedRecord) -> None:
        # UDP transports expose a drop-on-full semantics via the submit
        # return value; TCP transports rely on set_paused() toggling.
        submitted = self._sink.submit(record, src)
        if not submitted:
            # Inform the transport so it can count a drop (UDP only cares).
            counter = getattr(self._transport, "record_drops", None)
            if counter is not None:
                setattr(self._transport, "record_drops", counter + 1)

    def _handle_transport_event(self, event: dict[str, Any]) -> None:
        self._forward(event)

    def _handle_sink_event(self, event: dict[str, Any]) -> None:
        name = event.get("event")
        if name == "sink_high_watermark":
            # TCP pauses per-peer reads; UDP ignores (drop-on-submit already).
            self._transport.set_paused(True)
        elif name == "sink_low_watermark":
            self._transport.set_paused(False)
        self._forward(event)

    def _emit(self, event: str, **payload: Any) -> None:
        record = {"event": event, **payload}
        self._forward(record)

    def _forward(self, record: dict[str, Any]) -> None:
        self._state.events.append(record)
        if self._on_event is not None:
            self._on_event(record)
