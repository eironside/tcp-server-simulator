"""Controller boundary between tkinter UI and async engine/transport."""

from __future__ import annotations

import asyncio
import csv
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from queue import Queue
from typing import Any

from tcp_sim.engine.file_reader import FileReader
from tcp_sim.engine.framer import FramingMode
from tcp_sim.engine.receiver import ReceiverEngine
from tcp_sim.engine.scheduler import ScheduledMessage
from tcp_sim.engine.simulator import SimulatorEngine
from tcp_sim.engine.sink_writer import SinkConfig, SinkFormat
from tcp_sim.transport.tcp_client_receiver import (
    TcpClientReceiver,
    TcpClientReceiverConfig,
)
from tcp_sim.transport.tcp_client_sender import TcpClientConfig, TcpClientSender
from tcp_sim.transport.tcp_server_receiver import (
    TcpServerReceiver,
    TcpServerReceiverConfig,
)
from tcp_sim.transport.tcp_server_sender import TcpServerConfig, TcpServerSender
from tcp_sim.transport.udp_client_receiver import (
    UdpClientReceiver,
    UdpClientReceiverConfig,
)
from tcp_sim.transport.udp_client_sender import UdpClientConfig, UdpClientSender
from tcp_sim.transport.udp_server_receiver import (
    UdpServerReceiver,
    UdpServerReceiverConfig,
)
from tcp_sim.transport.udp_server_sender import UdpServerConfig, UdpServerSender


@dataclass
class RuntimeSettings:
    mode: str
    protocol: str
    host: str
    port: int
    connect_timeout_seconds: float = 10.0
    send_timeout_seconds: float = 10.0
    reconnect_max_backoff_seconds: float = 30.0
    use_tls: bool = False
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    tls_ca_file: str | None = None
    tls_verify: bool = True
    tls_server_hostname: str | None = None


@dataclass
class StreamSettings:
    file_path: str
    delimiter: str = ","
    has_header: bool = True
    send_header: bool = True
    rate_features_per_second: float = 10.0
    loop: bool = True
    line_ending: str = "\n"
    strip_lf: bool = False
    strip_cr: bool = False
    velocity_compatibility_mode: bool = False


@dataclass
class SinkSettings:
    enabled: bool = False
    path: str | None = None
    format: str = "jsonl"  # "jsonl" | "delimited"
    record_separator: bytes = b"\n"
    rotation_max_bytes: int = 100 * 1024 * 1024
    rotation_backup_count: int = 5
    queue_high_watermark_bytes: int = 8 * 1024 * 1024
    queue_low_watermark_bytes: int = 2 * 1024 * 1024
    queue_max_bytes: int = 32 * 1024 * 1024

    def to_sink_config(self) -> SinkConfig:
        return SinkConfig(
            enabled=self.enabled,
            path=self.path,
            format=SinkFormat(self.format),
            record_separator=self.record_separator,
            rotation_max_bytes=self.rotation_max_bytes,
            rotation_backup_count=self.rotation_backup_count,
            queue_high_watermark_bytes=self.queue_high_watermark_bytes,
            queue_low_watermark_bytes=self.queue_low_watermark_bytes,
            queue_max_bytes=self.queue_max_bytes,
        )


@dataclass
class ReceiverSettings:
    framing_mode: str = "lf"  # "lf" | "crlf" | "raw_chunk"
    max_record_bytes: int = 1 << 20
    # UDP-only knobs
    udp_multicast_group: str | None = None
    udp_multicast_interface: str = "0.0.0.0"
    udp_client_hello_payload: bytes | None = None
    udp_client_hello_interval_seconds: float = 0.0
    udp_client_filter_remote_peer: bool = False


class SimulatorController:
    """Owns async resources and exposes thread-safe control methods for tkinter."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._run_loop, daemon=True)
        self._loop_thread.start()

        self._status_queue: Queue[str] = Queue()
        self._active_transport: Any = None
        self._active_settings: RuntimeSettings | None = None
        self._stream_settings: StreamSettings | None = None
        self._engine: SimulatorEngine | None = None
        self._stats_task: asyncio.Task[None] | None = None
        self._line_controls: tuple[int | None, int | None, int | None] = (
            None,
            None,
            None,
        )
        # Receiver-role state. Mutually exclusive with sender state: the
        # controller enforces stop+rebind when the role toggles.
        self._receiver_engine: ReceiverEngine | None = None
        self._receiver_transport: Any = None
        self._receiver_stats_task: asyncio.Task[None] | None = None
        self._active_role: str = "sender"

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

    def start_transmission(
        self,
        settings: RuntimeSettings,
        stream_settings: StreamSettings,
    ) -> None:
        asyncio.run_coroutine_threadsafe(
            self._start_transmission_async(settings, stream_settings), self._loop
        )

    def apply_settings(self, settings: RuntimeSettings) -> None:
        asyncio.run_coroutine_threadsafe(
            self._apply_settings_async(settings), self._loop
        )

    async def _start_transmission_async(
        self,
        settings: RuntimeSettings,
        stream_settings: StreamSettings,
    ) -> None:
        try:
            stream_settings = self._apply_velocity_compatibility_preset(stream_settings)
            records, header_payload = self._load_records(stream_settings)

            if self._active_transport is not None:
                self._emit("Applying controlled stop/rebind transition...")
                await self._stop_transport_async()

            self._active_transport = self._build_transport(
                settings,
                send_header_on_connect=stream_settings.send_header,
                header_payload=header_payload,
            )
            self._active_settings = settings
            self._stream_settings = stream_settings

            await self._active_transport.start()
            self._emit(
                f"Transport started: {settings.mode}/{settings.protocol} on {settings.host}:{settings.port}"
            )

            if isinstance(self._active_transport, TcpServerSender):
                self._emit(
                    f"__connections__:{self._active_transport.connected_client_count}"
                )

            self._engine = SimulatorEngine(
                initial_records=records,
                send_callback=self._send_scheduled_message,
                rate_features_per_second=stream_settings.rate_features_per_second,
                loop=stream_settings.loop,
            )

            start_line, end_line, first_n = self._line_controls
            if start_line is not None or end_line is not None or first_n is not None:
                self._engine.set_line_controls(
                    start_line=start_line,
                    end_line=end_line,
                    first_n=first_n,
                )

            await self._engine.start()
            self._start_status_loop()

            self._emit(
                f"__progress__:{self._engine.scheduler.current_line}:{self._engine.scheduler.total_lines}"
            )
            self._emit("__rate__:0.0:0.0")
            self._emit("__sent__:0:0")
            self._emit(
                f"Transmission started with {len(records)} valid records from {stream_settings.file_path}."
            )
            if not records and not header_payload:
                self._emit(
                    "No valid records were loaded. Check delimiter/header settings and input file contents."
                )
        except (OSError, RuntimeError, ValueError, csv.Error) as exc:
            self._emit(f"Failed to start transmission: {exc}")
            await self._stop_transport_async()

    async def _apply_settings_async(self, settings: RuntimeSettings) -> None:
        if self._active_transport is not None:
            self._emit("Applying controlled stop/rebind transition...")
            await self._stop_transport_async()

        self._active_transport = self._build_transport(settings)
        self._active_settings = settings
        self._stream_settings = None

        await self._active_transport.start()
        self._emit(
            f"Transport started: {settings.mode}/{settings.protocol} on {settings.host}:{settings.port}"
        )

        if isinstance(self._active_transport, TcpServerSender):
            self._emit(
                f"__connections__:{self._active_transport.connected_client_count}"
            )

    def _build_transport(
        self,
        settings: RuntimeSettings,
        send_header_on_connect: bool = False,
        header_payload: bytes | None = None,
    ) -> Any:
        mode = settings.mode.lower()
        protocol = settings.protocol.lower()

        if protocol == "tcp" and mode == "server":
            return TcpServerSender(
                TcpServerConfig(
                    host=settings.host,
                    port=settings.port,
                    send_timeout_seconds=settings.send_timeout_seconds,
                    slow_client_timeout_seconds=settings.send_timeout_seconds,
                    send_header_on_connect=send_header_on_connect,
                    header_payload=header_payload,
                    use_tls=settings.use_tls,
                    tls_certfile=settings.tls_certfile,
                    tls_keyfile=settings.tls_keyfile,
                    tls_ca_file=settings.tls_ca_file,
                ),
                on_event=self._on_transport_event,
            )

        if protocol == "tcp" and mode == "client":
            return TcpClientSender(
                TcpClientConfig(
                    host=settings.host,
                    port=settings.port,
                    connect_timeout_seconds=settings.connect_timeout_seconds,
                    send_timeout_seconds=settings.send_timeout_seconds,
                    reconnect_max_backoff_seconds=settings.reconnect_max_backoff_seconds,
                    use_tls=settings.use_tls,
                    tls_ca_file=settings.tls_ca_file,
                    tls_verify=settings.tls_verify,
                    tls_server_hostname=settings.tls_server_hostname,
                ),
                on_event=self._on_transport_event,
            )

        if protocol == "udp" and mode == "server":
            return UdpServerSender(
                UdpServerConfig(
                    host=settings.host,
                    port=settings.port,
                ),
                on_event=self._on_transport_event,
            )

        if protocol == "udp" and mode == "client":
            return UdpClientSender(
                UdpClientConfig(host=settings.host, port=settings.port)
            )

        raise ValueError(f"Unsupported mode/protocol combination: {mode}/{protocol}")

    def stop_transport(self) -> None:
        asyncio.run_coroutine_threadsafe(self._stop_transport_async(), self._loop)

    def toggle_pause(self) -> None:
        self._loop.call_soon_threadsafe(self._toggle_pause)

    def step_once(self) -> None:
        asyncio.run_coroutine_threadsafe(self._step_once_async(), self._loop)

    def jump_to(self, line_number: int) -> None:
        self._loop.call_soon_threadsafe(self._jump_to_line, line_number)

    def update_rate(self, rate_features_per_second: float) -> None:
        self._loop.call_soon_threadsafe(self._update_rate, rate_features_per_second)

    def swap_file(
        self,
        file_path: str,
        delimiter: str,
        has_header: bool,
        send_header: bool,
        line_ending: str = "\n",
        strip_lf: bool = False,
        strip_cr: bool = False,
        velocity_compatibility_mode: bool = False,
    ) -> None:
        if self._stream_settings is None:
            self._emit("Cannot swap file before transmission has been started.")
            return

        updated = replace(
            self._stream_settings,
            file_path=file_path,
            delimiter=delimiter,
            has_header=has_header,
            send_header=send_header,
            line_ending=line_ending,
            strip_lf=strip_lf,
            strip_cr=strip_cr,
            velocity_compatibility_mode=velocity_compatibility_mode,
        )
        self._loop.call_soon_threadsafe(self._swap_file, updated)

    def set_line_controls(
        self,
        start_line: int | None,
        end_line: int | None,
        first_n: int | None,
    ) -> None:
        self._loop.call_soon_threadsafe(
            self._set_line_controls,
            start_line,
            end_line,
            first_n,
        )

    async def _stop_transport_async(self) -> None:
        if self._stats_task is not None:
            self._stats_task.cancel()
            await asyncio.gather(self._stats_task, return_exceptions=True)
            self._stats_task = None

        if self._engine is not None:
            await self._engine.stop()
            self._engine = None
            self._emit("Transmission stopped.")

        if self._active_transport is None:
            return

        await self._active_transport.stop()
        self._emit("Transport stopped.")
        self._active_transport = None
        self._active_settings = None
        self._emit("__connections__:0")
        self._emit("__progress__:0:0")
        self._emit("__rate__:0.0:0.0")
        self._emit("__sent__:0:0")

    def _toggle_pause(self) -> None:
        if self._engine is None:
            self._emit("No active transmission to pause/resume.")
            return

        if self._engine.scheduler.is_paused:
            self._engine.resume()
            self._emit("Transmission resumed.")
            return

        self._engine.pause()
        self._emit("Transmission paused.")

    async def _step_once_async(self) -> None:
        if self._engine is None:
            self._emit("No active transmission to step.")
            return

        message = self._engine.step()
        if message is None:
            self._emit("Step requested but no message is available.")
            return

        await self._send_scheduled_message(message)
        self._engine.stats.features_sent += 1
        self._engine.stats.bytes_sent += len(message.payload)

        if message.is_header:
            self._emit("Step sent header message.")
        else:
            self._emit(f"Step sent line {message.line_number}.")

    def _jump_to_line(self, line_number: int) -> None:
        if self._engine is None:
            self._emit("No active transmission to jump.")
            return

        try:
            self._engine.jump_to(line_number)
        except ValueError as exc:
            self._emit(f"Jump failed: {exc}")
            return

        self._emit(f"Jumped to line {line_number}.")

    def _update_rate(self, rate_features_per_second: float) -> None:
        if self._engine is None:
            self._emit("No active transmission to update rate.")
            return

        self._engine.update_rate(rate_features_per_second)
        if self._stream_settings is not None:
            self._stream_settings = replace(
                self._stream_settings,
                rate_features_per_second=rate_features_per_second,
            )
        self._emit(f"Rate updated to {rate_features_per_second:.2f} feat/s.")

    def _swap_file(self, stream_settings: StreamSettings) -> None:
        if self._engine is None:
            self._emit("Cannot swap file without an active transmission.")
            return

        stream_settings = self._apply_velocity_compatibility_preset(stream_settings)

        try:
            records, header_payload = self._load_records(stream_settings)
        except (OSError, RuntimeError, ValueError, csv.Error) as exc:
            self._emit(f"File swap failed: {exc}")
            return

        self._engine.swap_records(
            records,
            header_payload=header_payload if stream_settings.send_header else None,
        )
        self._stream_settings = stream_settings

        if isinstance(self._active_transport, TcpServerSender):
            transport: TcpServerSender = self._active_transport
            transport.update_header_payload(
                send_header_on_connect=stream_settings.send_header,
                header_payload=header_payload,
            )

        self._emit(
            f"File swap queued with {len(records)} valid records from {stream_settings.file_path}."
        )

    def _set_line_controls(
        self,
        start_line: int | None,
        end_line: int | None,
        first_n: int | None,
    ) -> None:
        self._line_controls = (start_line, end_line, first_n)

        if self._engine is not None:
            try:
                self._engine.set_line_controls(
                    start_line=start_line,
                    end_line=end_line,
                    first_n=first_n,
                )
            except ValueError as exc:
                self._emit(f"Line controls rejected: {exc}")
                return

        self._emit(
            "Line controls updated "
            f"(start={start_line}, end={end_line}, first_n={first_n})."
        )

    async def _send_scheduled_message(self, message: ScheduledMessage) -> None:
        if self._active_transport is None:
            return

        if isinstance(self._active_transport, TcpServerSender):
            has_broadcast_clients = self._active_transport.has_broadcast_clients
            wait_for_broadcast_clients = (
                self._active_transport.wait_for_broadcast_clients
            )

            while self._engine is not None and self._engine.is_running:
                if has_broadcast_clients():
                    break
                await wait_for_broadcast_clients()

            if not has_broadcast_clients():
                return

            await self._active_transport.broadcast(message.payload)
            return

        await self._active_transport.send(message.payload)

    def _start_status_loop(self) -> None:
        if self._stats_task is not None and not self._stats_task.done():
            return
        self._stats_task = asyncio.create_task(self._status_loop())

    async def _status_loop(self) -> None:
        last_features = 0
        last_bytes = 0
        last_timestamp = time.monotonic()

        while True:
            await asyncio.sleep(0.25)

            engine = self._engine
            if engine is None:
                return

            now = time.monotonic()
            elapsed_seconds = max(now - last_timestamp, 1e-6)

            feature_delta = engine.stats.features_sent - last_features
            byte_delta = engine.stats.bytes_sent - last_bytes
            features_per_second = feature_delta / elapsed_seconds
            kb_per_second = (byte_delta / 1024.0) / elapsed_seconds

            last_features = engine.stats.features_sent
            last_bytes = engine.stats.bytes_sent
            last_timestamp = now

            self._emit(
                f"__progress__:{engine.scheduler.current_line}:{engine.scheduler.total_lines}"
            )
            self._emit(f"__rate__:{features_per_second:.3f}:{kb_per_second:.3f}")
            self._emit(
                f"__sent__:{engine.stats.features_sent}:{engine.stats.bytes_sent}"
            )

    def _load_records(
        self,
        stream_settings: StreamSettings,
    ) -> tuple[list[bytes], bytes | None]:
        normalized_path = stream_settings.file_path.strip()
        if not normalized_path:
            raise ValueError("A data file must be selected before starting transport.")

        reader = FileReader(
            file_path=Path(normalized_path),
            delimiter=stream_settings.delimiter or ",",
            has_header=stream_settings.has_header,
        )
        if not reader.is_ready:
            raise ValueError(f"Data file not found: {normalized_path}")

        records = [row.raw_text.encode("utf-8") for row in reader.iter_valid_raw_rows()]
        records = [
            self._apply_payload_filters(payload, stream_settings) for payload in records
        ]

        header_payload: bytes | None = None
        if stream_settings.send_header and reader.header_raw is not None:
            header_payload = self._apply_payload_filters(
                reader.header_raw.encode("utf-8"),
                stream_settings,
            )

        return records, header_payload

    def _apply_payload_filters(
        self,
        payload: bytes,
        stream_settings: StreamSettings,
    ) -> bytes:
        filtered = payload
        if stream_settings.strip_cr:
            filtered = filtered.replace(b"\r", b"")
        if stream_settings.strip_lf:
            filtered = filtered.replace(b"\n", b"")
        return filtered

    def _apply_velocity_compatibility_preset(
        self,
        stream_settings: StreamSettings,
    ) -> StreamSettings:
        if not stream_settings.velocity_compatibility_mode:
            return stream_settings

        adjusted = stream_settings
        updates: list[str] = []

        if adjusted.send_header:
            adjusted = replace(adjusted, send_header=False)
            updates.append("send_header=False")

        if adjusted.strip_lf:
            adjusted = replace(adjusted, strip_lf=False)
            updates.append("strip_lf=False")

        if updates:
            self._emit(
                "Velocity compatibility preset applied: " + ", ".join(updates) + "."
            )
        else:
            self._emit("Velocity compatibility preset enabled.")

        return adjusted

    def _on_transport_event(self, event: dict[str, object]) -> None:
        name = str(event.get("event", ""))
        detail_parts = [
            f"{key}={value}" for key, value in event.items() if key != "event"
        ]

        details = ", ".join(detail_parts)
        if details:
            self._emit(f"{name}: {details}")
        else:
            self._emit(name)

        if isinstance(self._active_transport, TcpServerSender) and name in {
            "client_connect",
            "client_disconnect",
        }:
            self._emit(
                f"__connections__:{self._active_transport.connected_client_count}"
            )

    def shutdown(self) -> None:
        future = asyncio.run_coroutine_threadsafe(
            self._stop_everything_async(), self._loop
        )
        try:
            future.result(timeout=5)
        except (TimeoutError, asyncio.TimeoutError, RuntimeError):
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._loop_thread.join(timeout=3)

    # ----- Receiver role ---------------------------------------------------

    def start_reception(
        self,
        settings: RuntimeSettings,
        receiver_settings: ReceiverSettings,
        sink_settings: SinkSettings,
    ) -> None:
        asyncio.run_coroutine_threadsafe(
            self._start_reception_async(settings, receiver_settings, sink_settings),
            self._loop,
        )

    def stop_reception(self) -> None:
        asyncio.run_coroutine_threadsafe(self._stop_reception_async(), self._loop)

    def configure_sink(self, sink_settings: SinkSettings) -> None:
        asyncio.run_coroutine_threadsafe(
            self._configure_sink_async(sink_settings), self._loop
        )

    async def _start_reception_async(
        self,
        settings: RuntimeSettings,
        receiver_settings: ReceiverSettings,
        sink_settings: SinkSettings,
    ) -> None:
        try:
            # Role transition: tear down any sender state before rebinding.
            if self._active_transport is not None or self._engine is not None:
                self._emit("Switching to receiver role; stopping sender...")
                await self._stop_transport_async()
            if self._receiver_engine is not None:
                await self._stop_reception_async()

            transport = self._build_receiver_transport(settings, receiver_settings)
            engine = ReceiverEngine(
                transport,
                sink_settings.to_sink_config(),
                on_event=self._on_receiver_event,
            )
            self._receiver_transport = transport
            self._receiver_engine = engine
            self._active_settings = settings
            self._active_role = "receiver"

            await engine.start()
            self._emit(
                "Reception started: "
                f"{settings.mode}/{settings.protocol} on "
                f"{settings.host}:{settings.port}"
            )
            self._start_receiver_stats_loop()
        except (OSError, RuntimeError, ValueError) as exc:
            self._emit(f"Failed to start reception: {exc}")
            await self._stop_reception_async()

    async def _stop_reception_async(self) -> None:
        if self._receiver_stats_task is not None:
            self._receiver_stats_task.cancel()
            await asyncio.gather(self._receiver_stats_task, return_exceptions=True)
            self._receiver_stats_task = None
        if self._receiver_engine is not None:
            engine = self._receiver_engine
            # Always detach state first so a slow/hung stop() cannot leave
            # the controller wedged in "receiver-running" mode.
            self._receiver_engine = None
            self._receiver_transport = None
            try:
                await asyncio.wait_for(engine.stop(), timeout=5.0)
                self._emit("Reception stopped.")
            except asyncio.TimeoutError:
                self._emit(
                    "Reception stop timed out after 5s; forcing teardown. "
                    "Check JSON log for receiver_stop_timeout."
                )
            except Exception as exc:  # pragma: no cover - defensive
                self._emit(f"Reception stop raised: {exc!r}")
            self._emit("__receiver_records__:0:0")
            self._emit("__receiver_sink__:disabled:0:0")
        if self._active_role == "receiver":
            self._active_role = "sender"
            self._active_settings = None

    async def _configure_sink_async(self, sink_settings: SinkSettings) -> None:
        if self._receiver_engine is None:
            self._emit("No active receiver; sink configuration ignored.")
            return
        await self._receiver_engine.configure_sink(sink_settings.to_sink_config())
        self._emit(
            f"Sink reconfigured: enabled={sink_settings.enabled}, "
            f"format={sink_settings.format}, path={sink_settings.path}"
        )

    async def _stop_everything_async(self) -> None:
        await self._stop_reception_async()
        await self._stop_transport_async()

    def _build_receiver_transport(
        self,
        settings: RuntimeSettings,
        receiver_settings: ReceiverSettings,
    ) -> Any:
        mode = settings.mode.lower()
        protocol = settings.protocol.lower()
        framing = FramingMode(receiver_settings.framing_mode)

        if protocol == "tcp" and mode == "server":
            return TcpServerReceiver(
                TcpServerReceiverConfig(
                    host=settings.host,
                    port=settings.port,
                    framing_mode=framing,
                    max_record_bytes=receiver_settings.max_record_bytes,
                    use_tls=settings.use_tls,
                    tls_certfile=settings.tls_certfile,
                    tls_keyfile=settings.tls_keyfile,
                    tls_ca_file=settings.tls_ca_file,
                )
            )
        if protocol == "tcp" and mode == "client":
            return TcpClientReceiver(
                TcpClientReceiverConfig(
                    host=settings.host,
                    port=settings.port,
                    connect_timeout_seconds=settings.connect_timeout_seconds,
                    reconnect_max_backoff_seconds=settings.reconnect_max_backoff_seconds,
                    framing_mode=framing,
                    max_record_bytes=receiver_settings.max_record_bytes,
                    use_tls=settings.use_tls,
                    tls_ca_file=settings.tls_ca_file,
                    tls_verify=settings.tls_verify,
                    tls_server_hostname=settings.tls_server_hostname,
                )
            )
        if protocol == "udp" and mode == "server":
            return UdpServerReceiver(
                UdpServerReceiverConfig(
                    host=settings.host,
                    port=settings.port,
                    max_record_bytes=receiver_settings.max_record_bytes,
                    multicast_group=receiver_settings.udp_multicast_group,
                    multicast_interface=receiver_settings.udp_multicast_interface,
                )
            )
        if protocol == "udp" and mode == "client":
            return UdpClientReceiver(
                UdpClientReceiverConfig(
                    host=settings.host,
                    port=settings.port,
                    max_record_bytes=receiver_settings.max_record_bytes,
                    hello_payload=receiver_settings.udp_client_hello_payload,
                    hello_interval_seconds=(
                        receiver_settings.udp_client_hello_interval_seconds
                    ),
                    filter_remote_peer=receiver_settings.udp_client_filter_remote_peer,
                )
            )
        raise ValueError(
            f"Unsupported receiver mode/protocol combination: {mode}/{protocol}"
        )

    def _on_receiver_event(self, event: dict[str, object]) -> None:
        name = str(event.get("event", ""))
        detail_parts = [
            f"{key}={value}" for key, value in event.items() if key != "event"
        ]
        details = ", ".join(detail_parts)
        self._emit(f"{name}: {details}" if details else name)

    def _start_receiver_stats_loop(self) -> None:
        if (
            self._receiver_stats_task is not None
            and not self._receiver_stats_task.done()
        ):
            return
        self._receiver_stats_task = asyncio.create_task(self._receiver_stats_loop())

    async def _receiver_stats_loop(self) -> None:
        last_records = 0
        last_bytes = 0
        last_ts = time.monotonic()
        while True:
            await asyncio.sleep(0.25)
            engine = self._receiver_engine
            if engine is None:
                return
            now = time.monotonic()
            elapsed = max(now - last_ts, 1e-6)
            stats = engine.stats
            delta_records = stats.records_received - last_records
            delta_bytes = stats.bytes_received - last_bytes
            last_records = stats.records_received
            last_bytes = stats.bytes_received
            last_ts = now
            self._emit(
                f"__receiver_records__:{stats.records_received}:{stats.bytes_received}"
            )
            self._emit(
                f"__receiver_rate__:{delta_records / elapsed:.3f}:"
                f"{(delta_bytes / 1024.0) / elapsed:.3f}"
            )
            self._emit(
                "__receiver_sink__:"
                f"{'enabled' if stats.sink_enabled else 'disabled'}:"
                f"{stats.sink_records_written}:{stats.sink_bytes_written}"
            )
