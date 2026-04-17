"""Async sink writer for the receiver role.

Consumes `FramedRecord` objects from a bounded queue and persists them to a
rotating file in either delimited passthrough or JSON Lines format. All
file I/O happens on a dedicated background task so the hot receive path
never blocks on disk.

Runtime reconfiguration (enable/disable, format swap, path swap, rotation
policy) takes effect at the next record boundary without dropping in-flight
records.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Awaitable, Callable, Optional

from tcp_sim.engine.framer import FramedRecord
from tcp_sim.transport.base import EventCallback, EventEmitter


class SinkFormat(str, Enum):
    DELIMITED = "delimited"
    JSONL = "jsonl"


@dataclass
class SinkConfig:
    """Sink writer configuration. All fields are hot-swappable via `configure()`."""

    enabled: bool = False
    path: Optional[str] = None
    format: SinkFormat = SinkFormat.JSONL
    # For DELIMITED format: bytes appended after each record.
    record_separator: bytes = b"\n"
    rotation_max_bytes: int = 100 * 1024 * 1024
    rotation_backup_count: int = 5
    # Queue watermarks are measured in buffered payload bytes.
    queue_high_watermark_bytes: int = 8 * 1024 * 1024
    queue_low_watermark_bytes: int = 2 * 1024 * 1024
    # Hard cap on queued bytes; writes above this block (TCP) or drop (UDP).
    queue_max_bytes: int = 32 * 1024 * 1024

    def __post_init__(self) -> None:
        if self.rotation_max_bytes <= 0:
            raise ValueError("rotation_max_bytes must be > 0")
        if self.rotation_backup_count < 0:
            raise ValueError("rotation_backup_count must be >= 0")
        if self.queue_low_watermark_bytes < 0:
            raise ValueError("queue_low_watermark_bytes must be >= 0")
        if self.queue_high_watermark_bytes <= self.queue_low_watermark_bytes:
            raise ValueError(
                "queue_high_watermark_bytes must be > queue_low_watermark_bytes"
            )
        if self.queue_max_bytes < self.queue_high_watermark_bytes:
            raise ValueError("queue_max_bytes must be >= queue_high_watermark_bytes")


@dataclass
class SinkStats:
    records_written: int = 0
    bytes_written: int = 0
    rotations: int = 0
    records_dropped: int = 0
    queued_bytes: int = 0
    queued_records: int = 0
    current_path: Optional[str] = None
    current_file_size: int = 0
    backpressured: bool = False
    enabled: bool = False


@dataclass
class _QueueItem:
    record: FramedRecord
    src: str
    # Lifecycle sentinel for clean shutdown. When True the drain loop exits.
    stop: bool = False


@dataclass
class _PendingConfig:
    cfg: SinkConfig
    done: asyncio.Event = field(default_factory=asyncio.Event)


class SinkWriter(EventEmitter):
    """Background file-writer consuming FramedRecord via an async queue.

    Events emitted (via the `on_event` callback):

    - `sink_started` `{path, format}`
    - `sink_stopped` `{}`
    - `sink_rotated` `{path, backup_path}`
    - `sink_reconfigured` `{path, format, enabled}`
    - `sink_high_watermark` `{queued_bytes}`
    - `sink_low_watermark` `{queued_bytes}`
    - `sink_record_dropped` `{reason, src, bytes_len}`
    - `sink_error` `{error, path}`
    """

    def __init__(
        self,
        config: SinkConfig,
        *,
        on_event: Optional[EventCallback] = None,
    ) -> None:
        self._init_events(on_event)
        self._cfg = config
        self._queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        self._queued_bytes = 0
        self._stats = SinkStats(enabled=config.enabled, current_path=config.path)
        self._task: Optional[asyncio.Task[None]] = None
        self._fh = None  # type: ignore[var-annotated]
        self._current_path: Optional[Path] = None
        self._backpressured = False
        self._pending_config: Optional[_PendingConfig] = None
        self._stopping = False

    # ----- Public API ------------------------------------------------------

    @property
    def stats(self) -> SinkStats:
        self._stats.queued_bytes = self._queued_bytes
        self._stats.queued_records = self._queue.qsize()
        self._stats.backpressured = self._backpressured
        self._stats.enabled = self._cfg.enabled
        return self._stats

    @property
    def backpressured(self) -> bool:
        return self._backpressured

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="sink-writer")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopping = True
        # Sentinel tells the drain loop to exit after flushing current queue.
        await self._queue.put(_QueueItem(record=FramedRecord(b""), src="", stop=True))
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
        self._task = None
        self._close_file()
        self._emit_event("sink_stopped")

    async def configure(self, new_config: SinkConfig) -> None:
        """Swap config; takes effect at the next record boundary.

        If the writer task is not running this mutates config directly.
        """
        if self._task is None:
            self._cfg = new_config
            self._stats.enabled = new_config.enabled
            self._stats.current_path = new_config.path
            return
        pending = _PendingConfig(cfg=new_config)
        self._pending_config = pending
        # Poke the queue so the loop wakes up even when idle.
        await self._queue.put(_QueueItem(record=FramedRecord(b""), src="", stop=False))
        await pending.done.wait()

    def submit(self, record: FramedRecord, src: str) -> bool:
        """Non-blocking enqueue. Returns False if the record was dropped.

        UDP receivers should treat False as a drop; TCP receivers should
        check `backpressured` and pause reads instead.
        """
        if not self._cfg.enabled:
            return True  # silently no-op: sink disabled means "metrics only"
        size = len(record.payload)
        if self._queued_bytes + size > self._cfg.queue_max_bytes:
            self._stats.records_dropped += 1
            self._emit_event(
                "sink_record_dropped",
                reason="queue_full",
                src=src,
                bytes_len=size,
            )
            return False
        self._queued_bytes += size
        self._queue.put_nowait(_QueueItem(record=record, src=src))
        self._update_backpressure()
        return True

    # ----- Drain loop ------------------------------------------------------

    async def _run(self) -> None:
        try:
            self._open_file_if_enabled()
            if self._cfg.enabled and self._current_path is not None:
                self._emit_event(
                    "sink_started",
                    path=str(self._current_path),
                    format=self._cfg.format.value,
                )
            while True:
                item = await self._queue.get()
                # Handle pending reconfigure at record boundary.
                if self._pending_config is not None:
                    self._apply_pending_config()
                if item.stop:
                    break
                if item.record.payload == b"" and item.src == "":
                    # Wake-up sentinel from configure(); nothing to write.
                    continue
                if not self._cfg.enabled or self._fh is None:
                    # Disabled mid-flight: drop this record (and account for it
                    # in queued_bytes so backpressure clears).
                    self._queued_bytes -= len(item.record.payload)
                    self._update_backpressure()
                    continue
                try:
                    await self._write_record(item)
                except Exception as exc:  # pragma: no cover - OS failure path
                    self._emit_event(
                        "sink_error",
                        error=repr(exc),
                        path=str(self._current_path) if self._current_path else None,
                    )
                finally:
                    self._queued_bytes -= len(item.record.payload)
                    self._update_backpressure()
        finally:
            self._close_file()

    # ----- File handling ---------------------------------------------------

    def _open_file_if_enabled(self) -> None:
        if not self._cfg.enabled or not self._cfg.path:
            return
        path = Path(self._cfg.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(path, "ab", buffering=0)  # unbuffered append
        self._current_path = path
        self._stats.current_path = str(path)
        self._stats.current_file_size = path.stat().st_size if path.exists() else 0

    def _close_file(self) -> None:
        if self._fh is not None:
            try:
                self._fh.close()
            except Exception:
                pass
            self._fh = None

    def _rotate(self) -> None:
        if self._current_path is None or self._fh is None:
            return
        self._close_file()
        base = self._current_path
        backup_count = self._cfg.rotation_backup_count
        if backup_count > 0:
            # Shift .N-1 -> .N, ..., .1 -> .2, base -> .1
            for i in range(backup_count - 1, 0, -1):
                src = base.with_suffix(base.suffix + f".{i}")
                dst = base.with_suffix(base.suffix + f".{i + 1}")
                if src.exists():
                    if dst.exists():
                        dst.unlink()
                    os.replace(src, dst)
            rotated = base.with_suffix(base.suffix + ".1")
            if rotated.exists():
                rotated.unlink()
            os.replace(base, rotated)
            self._stats.rotations += 1
            self._emit_event(
                "sink_rotated",
                path=str(base),
                backup_path=str(rotated),
            )
        else:
            # No backups: truncate in place.
            base.unlink(missing_ok=True)
            self._stats.rotations += 1
            self._emit_event("sink_rotated", path=str(base), backup_path=None)
        self._fh = open(base, "ab", buffering=0)
        self._stats.current_file_size = 0

    async def _write_record(self, item: _QueueItem) -> None:
        assert self._fh is not None
        blob = self._encode(item)
        # Rotate before writing if this write would exceed the cap.
        if (
            self._stats.current_file_size > 0
            and self._stats.current_file_size + len(blob) > self._cfg.rotation_max_bytes
        ):
            self._rotate()
        self._fh.write(blob)
        self._stats.current_file_size += len(blob)
        self._stats.bytes_written += len(blob)
        self._stats.records_written += 1

    def _encode(self, item: _QueueItem) -> bytes:
        rec = item.record
        if self._cfg.format is SinkFormat.DELIMITED:
            return rec.payload + self._cfg.record_separator
        # JSONL
        try:
            payload_str = rec.payload.decode("utf-8")
            obj = {
                "ts": _now_iso(),
                "src": item.src,
                "bytes_len": len(rec.payload),
                "payload": payload_str,
                "truncated": rec.truncated,
            }
        except UnicodeDecodeError:
            obj = {
                "ts": _now_iso(),
                "src": item.src,
                "bytes_len": len(rec.payload),
                "payload": base64.b64encode(rec.payload).decode("ascii"),
                "truncated": rec.truncated,
                "encoding": "base64",
            }
        return (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")

    # ----- Reconfigure + backpressure --------------------------------------

    def _apply_pending_config(self) -> None:
        pending = self._pending_config
        if pending is None:
            return
        self._pending_config = None
        new_cfg = pending.cfg
        path_changed = new_cfg.path != self._cfg.path
        enabled_changed = new_cfg.enabled != self._cfg.enabled
        self._cfg = new_cfg
        if path_changed or enabled_changed:
            self._close_file()
            self._open_file_if_enabled()
        self._stats.enabled = new_cfg.enabled
        self._stats.current_path = new_cfg.path
        self._emit_event(
            "sink_reconfigured",
            path=new_cfg.path,
            format=new_cfg.format.value,
            enabled=new_cfg.enabled,
        )
        pending.done.set()

    def _update_backpressure(self) -> None:
        if (
            not self._backpressured
            and self._queued_bytes >= self._cfg.queue_high_watermark_bytes
        ):
            self._backpressured = True
            self._emit_event("sink_high_watermark", queued_bytes=self._queued_bytes)
        elif (
            self._backpressured
            and self._queued_bytes <= self._cfg.queue_low_watermark_bytes
        ):
            self._backpressured = False
            self._emit_event("sink_low_watermark", queued_bytes=self._queued_bytes)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
