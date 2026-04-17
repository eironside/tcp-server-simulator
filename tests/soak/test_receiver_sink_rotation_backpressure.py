"""TM-SOAK-03: Receiver sink rotation and backpressure stability.

Validates that the receiver pipeline survives sustained record pressure with
aggressive sink rotation and backpressure watermarks without deadlocking,
losing TCP data, or leaking memory.

The watermarks are deliberately tight (a few records wide) so that the
concurrent pressure from many peers is enough to cycle the high and low
watermarks inside a short CI window without any artificial slow-disk hack.

Assertions (scaled-down but structurally equivalent to the design threshold):
- Sink rotates at the configured threshold and retains at most
  ``rotation_backup_count`` backups on disk.
- Per-peer read-pause activates above the high watermark and clears below
  the low watermark (at least one full cycle observed).
- Records received equal records written to the sink (no TCP data loss).
- Memory growth stays within the soak budget.
"""

from __future__ import annotations

import asyncio
import time
import tracemalloc
from pathlib import Path

import pytest

from tcp_sim.engine.framer import FramingMode
from tcp_sim.engine.receiver import ReceiverEngine
from tcp_sim.engine.sink_writer import SinkConfig, SinkFormat
from tcp_sim.transport.tcp_server_receiver import (
    TcpServerReceiver,
    TcpServerReceiverConfig,
)
from tests.scenario_thresholds import (
    TM_SOAK_03_AGGREGATE_RATE,
    TM_SOAK_03_DURATION_SECONDS,
    TM_SOAK_03_MAX_MEMORY_DELTA_BYTES,
    TM_SOAK_03_MIN_ROTATIONS,
    TM_SOAK_03_PEER_COUNT,
)


async def _sender_task(
    host: str,
    port: int,
    duration_seconds: float,
    max_records: int,
    prefix: str,
    payload_body: bytes,
) -> int:
    _reader, writer = await asyncio.open_connection(host, port)
    sent = 0
    end_at = time.perf_counter() + duration_seconds
    try:
        while time.perf_counter() < end_at and sent < max_records:
            writer.write(f"{prefix}:{sent}:".encode("utf-8") + payload_body + b"\n")
            # Let TCP backpressure throttle us naturally; a blocked drain is
            # exactly the signal we want to observe here.
            await writer.drain()
            sent += 1
    finally:
        try:
            await writer.drain()
        except Exception:
            pass
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
    return sent


@pytest.mark.soak
@pytest.mark.asyncio
async def test_receiver_sink_rotation_backpressure_stability(tmp_path: Path) -> None:
    sink_path = tmp_path / "sink.jsonl"

    # Tight watermarks: a few records of buffered payload is enough to cross
    # the high watermark, and the low watermark is near-empty so natural
    # event-loop scheduling under 20 concurrent peers produces the required
    # cycle within the CI window.
    rotation_backup_count = 4
    sink_config = SinkConfig(
        enabled=True,
        path=str(sink_path),
        format=SinkFormat.JSONL,
        rotation_max_bytes=32 * 1024,
        rotation_backup_count=rotation_backup_count,
        queue_high_watermark_bytes=1024,
        queue_low_watermark_bytes=128,
        queue_max_bytes=2 * 1024 * 1024,
    )

    events: list[dict] = []

    def _capture(event: dict) -> None:
        events.append(event)

    transport = TcpServerReceiver(
        TcpServerReceiverConfig(
            host="127.0.0.1",
            port=0,
            framing_mode=FramingMode.LF,
            max_record_bytes=4096,
            read_chunk_bytes=4096,
        )
    )
    engine = ReceiverEngine(transport, sink_config, on_event=_capture)

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    await engine.start()
    bound_port = transport._server.sockets[0].getsockname()[1]  # type: ignore[union-attr]

    peer_count = max(TM_SOAK_03_PEER_COUNT, 4)
    duration = max(TM_SOAK_03_DURATION_SECONDS, 0.5)
    _ = TM_SOAK_03_AGGREGATE_RATE  # reserved for extended-profile overrides

    payload_body = b"x" * 128
    records_per_peer = 150

    tasks = [
        asyncio.create_task(
            _sender_task(
                "127.0.0.1",
                bound_port,
                duration,
                records_per_peer,
                f"p{idx}",
                payload_body,
            )
        )
        for idx in range(peer_count)
    ]

    sent_counts = await asyncio.gather(*tasks, return_exceptions=True)
    total_sent = sum(c for c in sent_counts if isinstance(c, int))

    drain_deadline = time.perf_counter() + 30.0
    while time.perf_counter() < drain_deadline:
        stats = engine.stats
        if (
            stats.records_received == total_sent
            and stats.sink_records_written == stats.records_received
        ):
            break
        await asyncio.sleep(0.05)

    final_stats = engine.stats
    await engine.stop()

    snapshot_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    mem_before = sum(s.size for s in snapshot_before.statistics("filename"))
    mem_after = sum(s.size for s in snapshot_after.statistics("filename"))
    memory_delta = mem_after - mem_before

    high_events = [e for e in events if e.get("event") == "sink_high_watermark"]
    low_events = [e for e in events if e.get("event") == "sink_low_watermark"]
    rotation_events = [e for e in events if e.get("event") == "sink_rotated"]

    # Primary soak invariants.
    assert total_sent > 0, "no records were actually sent"
    assert (
        final_stats.records_received == total_sent
    ), f"TCP data loss: sent={total_sent}, received={final_stats.records_received}"
    assert final_stats.sink_records_written == final_stats.records_received, (
        "sink drain incomplete: "
        f"received={final_stats.records_received}, "
        f"written={final_stats.sink_records_written}"
    )
    assert final_stats.sink_records_dropped == 0, (
        f"sink dropped records under TCP backpressure: "
        f"{final_stats.sink_records_dropped}"
    )

    # Rotation behavior.
    assert final_stats.sink_rotations >= TM_SOAK_03_MIN_ROTATIONS, (
        f"expected at least {TM_SOAK_03_MIN_ROTATIONS} rotations, "
        f"got {final_stats.sink_rotations}"
    )
    assert len(rotation_events) == final_stats.sink_rotations

    backup_files = sorted(
        p for p in sink_path.parent.glob(f"{sink_path.name}.*") if p.is_file()
    )
    assert len(backup_files) <= rotation_backup_count, (
        f"retained more backups than configured: {len(backup_files)} "
        f"> {rotation_backup_count}"
    )

    # Backpressure cycling (at least one full high->low transition observed).
    assert len(high_events) >= 1, "high watermark never fired under soak load"
    assert len(low_events) >= 1, "low watermark never cleared under soak load"

    # Resource budget.
    assert memory_delta <= TM_SOAK_03_MAX_MEMORY_DELTA_BYTES, (
        f"memory delta {memory_delta} exceeds budget "
        f"{TM_SOAK_03_MAX_MEMORY_DELTA_BYTES}"
    )

    assert sink_path.exists()
    assert sink_path.stat().st_size > 0
