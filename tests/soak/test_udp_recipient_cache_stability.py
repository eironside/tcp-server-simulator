import asyncio
import socket
import time
import tracemalloc

import pytest

from tcp_sim.transport.udp_server import UdpServer, UdpServerConfig
from tests.scenario_thresholds import (
    TM_SOAK_02_DURATION_SECONDS,
    TM_SOAK_02_MAX_MEMORY_DELTA_BYTES,
    TM_SOAK_02_UNIQUE_SENDERS,
)


@pytest.mark.soak
@pytest.mark.asyncio
async def test_udp_reply_to_senders_cache_stability_thresholds() -> None:
    cache_cap = 256
    ttl_seconds = 0.4
    cleanup_interval_seconds = 0.05

    server = UdpServer(
        UdpServerConfig(
            host="127.0.0.1",
            port=0,
            recipient_mode="reply_to_senders",
            recipient_cache_ttl_seconds=ttl_seconds,
            recipient_cache_max_entries=cache_cap,
            recipient_cache_cleanup_interval_seconds=cleanup_interval_seconds,
        )
    )
    await server.start()

    target_duration = max(TM_SOAK_02_DURATION_SECONDS, 0.1)
    unique_sender_target = max(TM_SOAK_02_UNIQUE_SENDERS, cache_cap + 1)

    sender_count = 0
    max_recipient_count = 0
    started_at = time.perf_counter()
    snapshot_after = None

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    try:
        while (time.perf_counter() - started_at) < target_duration or sender_count < unique_sender_target:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.bind(("127.0.0.1", 0))
                sock.sendto(b"probe", ("127.0.0.1", server.bound_port))
            finally:
                sock.close()

            sender_count += 1
            max_recipient_count = max(max_recipient_count, server.recipient_count)
            assert server.recipient_count <= cache_cap

            if sender_count % 100 == 0:
                await asyncio.sleep(0)

        await server.send(b"reply")
        await asyncio.sleep(ttl_seconds + cleanup_interval_seconds + 0.1)
        server.cleanup_expired()

        snapshot_after = tracemalloc.take_snapshot()
    finally:
        tracemalloc.stop()
        await server.stop()

    assert snapshot_after is not None
    mem_before = sum(stat.size for stat in snapshot_before.statistics("filename"))
    mem_after = sum(stat.size for stat in snapshot_after.statistics("filename"))
    memory_delta = mem_after - mem_before

    assert sender_count >= unique_sender_target
    assert max_recipient_count <= cache_cap
    assert any(event.get("event") == "udp_recipient_evicted" for event in server.events)
    assert memory_delta <= TM_SOAK_02_MAX_MEMORY_DELTA_BYTES
    assert server.recipient_count == 0
