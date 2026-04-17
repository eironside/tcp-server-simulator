"""Integration tests for UDP receivers + engine. Completes TM-INT-04."""

from __future__ import annotations

import asyncio
import socket
from pathlib import Path

import pytest

from tcp_sim.engine.receiver import ReceiverEngine
from tcp_sim.engine.sink_writer import SinkConfig, SinkFormat
from tcp_sim.transport.udp_client_receiver import (
    UdpClientReceiver,
    UdpClientReceiverConfig,
)
from tcp_sim.transport.udp_server_receiver import (
    UdpServerReceiver,
    UdpServerReceiverConfig,
)


def _reserve_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _wait_until(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_server_receiver_consumes_each_datagram_as_record() -> None:
    received: list[tuple[str, bytes]] = []
    port = _reserve_udp_port()

    receiver = UdpServerReceiver(
        UdpServerReceiverConfig(host="127.0.0.1", port=port),
        on_record=lambda src, rec: received.append((src, rec.payload)),
    )
    await receiver.start()
    try:
        loop = asyncio.get_event_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        for payload in (b"one", b"two", b"three"):
            transport.sendto(payload, ("127.0.0.1", port))

        assert await _wait_until(lambda: len(received) >= 3)
        assert {p for _, p in received} == {b"one", b"two", b"three"}
        transport.close()
    finally:
        await receiver.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_server_receiver_truncates_oversized_datagram() -> None:
    received: list = []
    port = _reserve_udp_port()

    receiver = UdpServerReceiver(
        UdpServerReceiverConfig(host="127.0.0.1", port=port, max_record_bytes=8),
        on_record=lambda src, rec: received.append(rec),
    )
    await receiver.start()
    try:
        loop = asyncio.get_event_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        transport.sendto(b"0123456789ABCDEF", ("127.0.0.1", port))

        assert await _wait_until(lambda: len(received) >= 1)
        rec = received[0]
        assert rec.truncated is True
        assert rec.payload == b"01234567"
        assert receiver.truncations == 1
        transport.close()
    finally:
        await receiver.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_client_receiver_sends_hello_and_receives_reply() -> None:
    received: list[bytes] = []
    # "publisher" that waits for a hello then replies.
    publisher_port = _reserve_udp_port()

    hello_received = asyncio.Event()
    sender_addr: list[tuple[str, int]] = []

    class _Pub(asyncio.DatagramProtocol):
        def __init__(self) -> None:
            self.transport: asyncio.DatagramTransport | None = None

        def connection_made(self, transport: asyncio.BaseTransport) -> None:
            self.transport = transport  # type: ignore[assignment]

        def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
            if data == b"HELLO":
                sender_addr.append(addr)
                hello_received.set()
                assert self.transport is not None
                for msg in (b"evt-1", b"evt-2"):
                    self.transport.sendto(msg, addr)

    loop = asyncio.get_event_loop()
    pub_transport, _ = await loop.create_datagram_endpoint(
        _Pub, local_addr=("127.0.0.1", publisher_port)
    )

    receiver = UdpClientReceiver(
        UdpClientReceiverConfig(
            host="127.0.0.1",
            port=publisher_port,
            hello_payload=b"HELLO",
        ),
        on_record=lambda src, rec: received.append(rec.payload),
    )
    await receiver.start()
    try:
        await asyncio.wait_for(hello_received.wait(), timeout=2.0)
        assert await _wait_until(lambda: len(received) >= 2)
        assert received == [b"evt-1", b"evt-2"]
    finally:
        await receiver.stop()
        pub_transport.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_client_receiver_filter_remote_peer_drops_strangers() -> None:
    received: list[bytes] = []
    publisher_port = _reserve_udp_port()

    # Start a "publisher" endpoint that won't actually reply; we'll just use
    # its address as the "expected" peer. Bind something else to inject from.
    loop = asyncio.get_event_loop()
    stranger_transport, _ = await loop.create_datagram_endpoint(
        asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
    )

    receiver = UdpClientReceiver(
        UdpClientReceiverConfig(
            host="127.0.0.1",
            port=publisher_port,
            filter_remote_peer=True,
        ),
        on_record=lambda src, rec: received.append(rec.payload),
    )
    await receiver.start()
    try:
        sockname = receiver._transport.get_extra_info("sockname")  # type: ignore[union-attr]
        assert sockname is not None
        # Send from a stranger address — should be filtered.
        stranger_transport.sendto(b"nope", ("127.0.0.1", int(sockname[1])))
        await asyncio.sleep(0.1)
        assert received == []
        assert receiver.packets_filtered == 1
    finally:
        await receiver.stop()
        stranger_transport.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_receiver_engine_writes_sink_delimited(tmp_path: Path) -> None:
    sink_path = tmp_path / "udp.log"
    port = _reserve_udp_port()
    transport = UdpServerReceiver(UdpServerReceiverConfig(host="127.0.0.1", port=port))
    engine = ReceiverEngine(
        transport,
        SinkConfig(
            enabled=True,
            path=str(sink_path),
            format=SinkFormat.DELIMITED,
            record_separator=b"\n",
        ),
    )
    await engine.start()
    try:
        loop = asyncio.get_event_loop()
        client_transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        for payload in (b"red", b"green", b"blue"):
            client_transport.sendto(payload, ("127.0.0.1", port))

        assert await _wait_until(
            lambda: engine.stats.sink_records_written >= 3, timeout=2.0
        )
        client_transport.close()
    finally:
        await engine.stop()

    contents = sink_path.read_bytes().splitlines()
    assert set(contents) == {b"red", b"green", b"blue"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_receiver_engine_drops_on_queue_full(tmp_path: Path) -> None:
    # Very tight sink queue so UDP floods trigger drops.
    port = _reserve_udp_port()
    transport = UdpServerReceiver(UdpServerReceiverConfig(host="127.0.0.1", port=port))
    engine = ReceiverEngine(
        transport,
        SinkConfig(
            enabled=True,
            path=str(tmp_path / "q.log"),
            format=SinkFormat.DELIMITED,
            record_separator=b"",
            queue_low_watermark_bytes=1,
            queue_high_watermark_bytes=2,
            queue_max_bytes=3,
        ),
    )
    await engine.start()
    try:
        loop = asyncio.get_event_loop()
        client_transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        payload = b"XXXX"  # 4 bytes > queue_max_bytes=3
        # Send many before the drain loop can keep up.
        for _ in range(50):
            client_transport.sendto(payload, ("127.0.0.1", port))

        assert await _wait_until(lambda: transport.record_drops > 0, timeout=2.0)
        assert transport.record_drops > 0
        client_transport.close()
    finally:
        await engine.stop()
