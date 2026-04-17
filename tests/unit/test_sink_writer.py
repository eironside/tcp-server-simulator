"""Unit tests for `tcp_sim.engine.sink_writer`."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path

import pytest

from tcp_sim.engine.framer import FramedRecord
from tcp_sim.engine.sink_writer import SinkConfig, SinkFormat, SinkWriter


async def _drain(writer: SinkWriter) -> None:
    """Wait until the sink writer's queue is empty."""
    for _ in range(200):
        if writer.stats.queued_records == 0:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("sink writer did not drain in time")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_delimited_passthrough_writes_verbatim(tmp_path: Path) -> None:
    path = tmp_path / "out.txt"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        )
    )
    await writer.start()
    writer.submit(FramedRecord(b"alpha"), src="127.0.0.1:1")
    writer.submit(FramedRecord(b"beta"), src="127.0.0.1:1")
    await _drain(writer)
    await writer.stop()

    assert path.read_bytes() == b"alpha\nbeta\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jsonl_format_utf8_payload(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    writer = SinkWriter(
        SinkConfig(enabled=True, path=str(path), format=SinkFormat.JSONL)
    )
    await writer.start()
    writer.submit(FramedRecord(b"hello"), src="peerA")
    writer.submit(FramedRecord(b"world", truncated=True), src="peerB")
    await _drain(writer)
    await writer.stop()

    lines = path.read_text(encoding="utf-8").splitlines()
    obj0 = json.loads(lines[0])
    obj1 = json.loads(lines[1])
    assert obj0["payload"] == "hello"
    assert obj0["src"] == "peerA"
    assert obj0["bytes_len"] == 5
    assert obj0["truncated"] is False
    assert "encoding" not in obj0
    assert obj1["truncated"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_jsonl_base64_fallback_for_non_utf8(tmp_path: Path) -> None:
    path = tmp_path / "out.jsonl"
    writer = SinkWriter(
        SinkConfig(enabled=True, path=str(path), format=SinkFormat.JSONL)
    )
    await writer.start()
    blob = b"\xff\xfe\xfd\x00\x01"
    writer.submit(FramedRecord(blob), src="peer")
    await _drain(writer)
    await writer.stop()

    obj = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert obj["encoding"] == "base64"
    assert base64.b64decode(obj["payload"]) == blob
    assert obj["bytes_len"] == len(blob)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rotation_by_size(tmp_path: Path) -> None:
    path = tmp_path / "rot.log"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
            rotation_max_bytes=20,
            rotation_backup_count=2,
        )
    )
    await writer.start()
    for i in range(6):
        writer.submit(FramedRecord(f"record{i}".encode("utf-8")), src="p")
    await _drain(writer)
    await writer.stop()

    # We should have the primary file plus at least one backup.
    assert path.exists()
    assert Path(str(path) + ".1").exists()
    assert writer.stats.rotations >= 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rotation_backup_count_cap(tmp_path: Path) -> None:
    path = tmp_path / "rot.log"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
            rotation_max_bytes=10,
            rotation_backup_count=2,
        )
    )
    await writer.start()
    for i in range(20):
        writer.submit(FramedRecord(f"r{i:03d}".encode()), src="p")
    await _drain(writer)
    await writer.stop()

    # Only backup_count backups may exist.
    assert Path(str(path) + ".1").exists()
    assert Path(str(path) + ".2").exists()
    assert not Path(str(path) + ".3").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_path_swap(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(first),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        )
    )
    await writer.start()
    writer.submit(FramedRecord(b"one"), src="p")
    await _drain(writer)

    await writer.configure(
        SinkConfig(
            enabled=True,
            path=str(second),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        )
    )
    writer.submit(FramedRecord(b"two"), src="p")
    await _drain(writer)
    await writer.stop()

    assert first.read_bytes() == b"one\n"
    assert second.read_bytes() == b"two\n"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_format_swap(tmp_path: Path) -> None:
    path = tmp_path / "fmt.log"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        )
    )
    await writer.start()
    writer.submit(FramedRecord(b"raw1"), src="p")
    await _drain(writer)

    await writer.configure(
        SinkConfig(enabled=True, path=str(path), format=SinkFormat.JSONL)
    )
    writer.submit(FramedRecord(b"json1"), src="peerX")
    await _drain(writer)
    await writer.stop()

    lines = path.read_bytes().splitlines()
    assert lines[0] == b"raw1"
    obj = json.loads(lines[1].decode("utf-8"))
    assert obj["payload"] == "json1"
    assert obj["src"] == "peerX"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_runtime_disable_stops_writing(tmp_path: Path) -> None:
    path = tmp_path / "dis.log"
    writer = SinkWriter(
        SinkConfig(
            enabled=True,
            path=str(path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        )
    )
    await writer.start()
    writer.submit(FramedRecord(b"pre"), src="p")
    await _drain(writer)

    await writer.configure(
        SinkConfig(enabled=False, path=str(path), format=SinkFormat.DELIMITED)
    )
    # While disabled submit() is a no-op; stats.records_dropped must NOT bump.
    writer.submit(FramedRecord(b"never"), src="p")
    await _drain(writer)
    await writer.stop()

    assert path.read_bytes() == b"pre\n"
    assert writer.stats.records_dropped == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_watermark_events(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    path = tmp_path / "wm.log"
    # Tiny watermarks so a handful of records trips them.
    config = SinkConfig(
        enabled=True,
        path=str(path),
        format=SinkFormat.DELIMITED,
        record_separator=b"",
        queue_low_watermark_bytes=2,
        queue_high_watermark_bytes=10,
        queue_max_bytes=10_000,
    )
    # Build writer but never start it — submit() fills the queue synchronously.
    writer = SinkWriter(config, on_event=events.append)
    for _ in range(5):
        writer.submit(FramedRecord(b"xxxx"), src="p")  # 4 bytes each
    names = [e["event"] for e in events]
    assert "sink_high_watermark" in names
    assert writer.backpressured is True

    # Now start the writer to drain and clear the backpressure.
    await writer.start()
    await _drain(writer)
    await writer.stop()

    names = [e["event"] for e in events]
    assert "sink_low_watermark" in names
    assert writer.backpressured is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_submit_drops_when_queue_full(tmp_path: Path) -> None:
    events: list[dict[str, object]] = []
    config = SinkConfig(
        enabled=True,
        path=str(tmp_path / "q.log"),
        format=SinkFormat.DELIMITED,
        queue_low_watermark_bytes=1,
        queue_high_watermark_bytes=2,
        queue_max_bytes=10,
    )
    writer = SinkWriter(config, on_event=events.append)
    assert writer.submit(FramedRecord(b"12345"), src="p") is True
    assert writer.submit(FramedRecord(b"67890"), src="p") is True
    # 11 bytes queued would exceed queue_max_bytes=10: must drop.
    assert writer.submit(FramedRecord(b"X"), src="p") is False
    assert writer.stats.records_dropped == 1
    assert any(e["event"] == "sink_record_dropped" for e in events)


@pytest.mark.unit
def test_sink_config_validates_watermarks() -> None:
    with pytest.raises(ValueError):
        SinkConfig(queue_low_watermark_bytes=10, queue_high_watermark_bytes=5)
    with pytest.raises(ValueError):
        SinkConfig(
            queue_low_watermark_bytes=1,
            queue_high_watermark_bytes=10,
            queue_max_bytes=5,
        )
    with pytest.raises(ValueError):
        SinkConfig(rotation_max_bytes=0)
