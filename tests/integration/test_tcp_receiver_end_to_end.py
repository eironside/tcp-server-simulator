"""Integration tests for the TCP receiver transports and engine.

Covers FR-56 / FR-57 / FR-60 / FR-63 / FR-64 / FR-68 / FR-70 (TCP half of TM-INT-04).
"""

from __future__ import annotations

import asyncio
import json
import socket
from contextlib import suppress
from pathlib import Path

import pytest

from tcp_sim.engine.framer import FramingMode
from tcp_sim.engine.receiver import ReceiverEngine
from tcp_sim.engine.sink_writer import SinkConfig, SinkFormat
from tcp_sim.transport.tcp_client_receiver import (
    TcpClientReceiver,
    TcpClientReceiverConfig,
)
from tcp_sim.transport.tcp_server_receiver import (
    TcpServerReceiver,
    TcpServerReceiverConfig,
)


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_until(predicate, timeout: float = 3.0, interval: float = 0.02) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_server_receiver_reads_records_from_single_peer() -> None:
    received: list[tuple[str, bytes]] = []
    port = _reserve_port()

    receiver = TcpServerReceiver(
        TcpServerReceiverConfig(host="127.0.0.1", port=port),
        on_record=lambda src, rec: received.append((src, rec.payload)),
    )
    await receiver.start()
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"alpha\nbeta\ngamma\n")
        await writer.drain()

        assert await _wait_until(lambda: len(received) >= 3)
        payloads = [p for _, p in received]
        assert payloads == [b"alpha", b"beta", b"gamma"]
        assert all(src.startswith("127.0.0.1:") for src, _ in received)
        assert receiver.records_received == 3
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
    finally:
        await receiver.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_server_receiver_handles_partial_chunk_and_multiple_peers() -> None:
    received: list[tuple[str, bytes]] = []
    port = _reserve_port()

    receiver = TcpServerReceiver(
        TcpServerReceiverConfig(host="127.0.0.1", port=port),
        on_record=lambda src, rec: received.append((src, rec.payload)),
    )
    await receiver.start()
    try:
        r1, w1 = await asyncio.open_connection("127.0.0.1", port)
        r2, w2 = await asyncio.open_connection("127.0.0.1", port)

        # Interleaved partial writes — framer must buffer correctly per peer.
        w1.write(b"one\ntw")
        w2.write(b"AAA\nBBB")
        await w1.drain()
        await w2.drain()
        w1.write(b"o\nthree\n")
        w2.write(b"\nCCC\n")
        await w1.drain()
        await w2.drain()

        assert await _wait_until(lambda: len(received) >= 6)
        per_peer: dict[str, list[bytes]] = {}
        for src, payload in received:
            per_peer.setdefault(src, []).append(payload)
        peers = list(per_peer.keys())
        assert len(peers) == 2
        # Each peer should see its own records in order, with no cross-talk.
        combined = {tuple(v) for v in per_peer.values()}
        assert (b"one", b"two", b"three") in combined
        assert (b"AAA", b"BBB", b"CCC") in combined

        for w in (w1, w2):
            w.close()
            with suppress(OSError):
                await w.wait_closed()
    finally:
        await receiver.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_client_receiver_reads_records_and_reconnects() -> None:
    received: list[tuple[str, bytes]] = []
    port = _reserve_port()
    clients_writers: list[asyncio.StreamWriter] = []

    async def _serve(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        clients_writers.append(writer)
        try:
            # Just hold the connection open until closed from outside.
            await reader.read()
        finally:
            with suppress(OSError, RuntimeError):
                await writer.wait_closed()

    server = await asyncio.start_server(_serve, "127.0.0.1", port)

    receiver = TcpClientReceiver(
        TcpClientReceiverConfig(
            host="127.0.0.1",
            port=port,
            reconnect_max_backoff_seconds=0.2,
            connect_timeout_seconds=0.5,
        ),
        on_record=lambda src, rec: received.append((src, rec.payload)),
    )
    await receiver.start()
    try:
        await asyncio.wait_for(receiver.connected_event.wait(), timeout=2.0)
        # First burst
        assert clients_writers, "server never accepted the client"
        w = clients_writers[0]
        w.write(b"red\ngreen\nblue\n")
        await w.drain()
        assert await _wait_until(lambda: len(received) >= 3)

        # Drop the connection to force a reconnect.
        w.close()
        with suppress(OSError, RuntimeError):
            await w.wait_closed()
        receiver.connected_event.clear()

        await asyncio.wait_for(receiver.connected_event.wait(), timeout=3.0)
        assert len(clients_writers) >= 2
        w2 = clients_writers[-1]
        w2.write(b"again\n")
        await w2.drain()
        assert await _wait_until(lambda: len(received) >= 4)
        assert received[-1][1] == b"again"
        assert receiver.reconnect_count >= 1
    finally:
        await receiver.stop()
        for w in clients_writers:
            w.close()
            with suppress(OSError, RuntimeError):
                await w.wait_closed()
        server.close()
        await server.wait_closed()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_receiver_engine_writes_sink_jsonl(tmp_path: Path) -> None:
    sink_path = tmp_path / "records.jsonl"
    port = _reserve_port()
    transport = TcpServerReceiver(
        TcpServerReceiverConfig(
            host="127.0.0.1", port=port, framing_mode=FramingMode.LF
        )
    )
    engine = ReceiverEngine(
        transport,
        SinkConfig(
            enabled=True,
            path=str(sink_path),
            format=SinkFormat.JSONL,
        ),
    )
    await engine.start()
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"hello\nworld\n")
        await writer.drain()

        assert await _wait_until(lambda: engine.stats.sink_records_written >= 2)
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
    finally:
        await engine.stop()

    lines = sink_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    obj0 = json.loads(lines[0])
    obj1 = json.loads(lines[1])
    assert {obj0["payload"], obj1["payload"]} == {"hello", "world"}
    assert obj0["truncated"] is False
    assert obj0["src"].startswith("127.0.0.1:")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_receiver_engine_runtime_path_swap(tmp_path: Path) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    port = _reserve_port()
    transport = TcpServerReceiver(TcpServerReceiverConfig(host="127.0.0.1", port=port))
    engine = ReceiverEngine(
        transport,
        SinkConfig(
            enabled=True,
            path=str(first),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        ),
    )
    await engine.start()
    try:
        _, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"one\n")
        await writer.drain()

        assert await _wait_until(lambda: engine.stats.sink_records_written >= 1)

        await engine.configure_sink(
            SinkConfig(
                enabled=True,
                path=str(second),
                format=SinkFormat.DELIMITED,
                record_separator=b"\n",
            )
        )

        writer.write(b"two\n")
        await writer.drain()

        assert await _wait_until(lambda: engine.stats.sink_records_written >= 2)
        writer.close()
        with suppress(OSError):
            await writer.wait_closed()
    finally:
        await engine.stop()

    assert first.read_bytes() == b"one\n"
    assert second.read_bytes() == b"two\n"
