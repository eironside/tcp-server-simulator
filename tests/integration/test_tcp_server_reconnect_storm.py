import asyncio
import time
import tracemalloc

import pytest

from tcp_sim.transport.tcp_server_sender import TcpServerConfig, TcpServerSender
from tests.scenario_thresholds import (
    TM_INT_01_CONNECTION_ROUNDS,
    TM_INT_01_MAX_ELAPSED_SECONDS,
    TM_INT_01_MAX_MEMORY_DELTA_BYTES,
    TM_INT_01_MIN_SUCCESS_RATIO,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_server_reconnect_storm_lifecycle() -> None:
    server = TcpServerSender(TcpServerConfig(host="127.0.0.1", port=0))
    await server.start()

    try:
        attempts = TM_INT_01_CONNECTION_ROUNDS
        successful_connections = 0

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()
        started_at = time.perf_counter()

        for _ in range(attempts):
            try:
                reader, writer = await asyncio.open_connection(
                    "127.0.0.1", server.listening_port
                )
                writer.close()
                await writer.wait_closed()
                del reader
                successful_connections += 1
            except OSError:
                continue

        elapsed_seconds = time.perf_counter() - started_at
        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        await asyncio.sleep(0.1)
        memory_before = sum(
            stat.size for stat in snapshot_before.statistics("filename")
        )
        memory_after = sum(stat.size for stat in snapshot_after.statistics("filename"))
        memory_delta = memory_after - memory_before

        success_ratio = successful_connections / attempts

        assert success_ratio >= TM_INT_01_MIN_SUCCESS_RATIO
        assert elapsed_seconds <= TM_INT_01_MAX_ELAPSED_SECONDS
        assert memory_delta <= TM_INT_01_MAX_MEMORY_DELTA_BYTES
        assert server.connected_client_count == 0
        assert (
            sum(1 for item in server.events if item["event"] == "client_connect")
            >= successful_connections
        )
    finally:
        await server.stop()
        await server.stop()
