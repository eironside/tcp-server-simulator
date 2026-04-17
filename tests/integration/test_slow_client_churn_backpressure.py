import asyncio
import time

import pytest

from tcp_sim.transport.tcp_server_sender import TcpServerConfig, TcpServerSender
from tests.scenario_thresholds import (
    TM_INT_03_BROADCAST_ITERATIONS,
    TM_INT_03_MAX_BROADCAST_SECONDS,
    TM_INT_03_MIN_FAST_BYTES,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_slow_client_is_disconnected_without_global_stall() -> None:
    server = TcpServerSender(
        TcpServerConfig(
            host="127.0.0.1",
            port=0,
            send_timeout_seconds=1.0,
            slow_client_timeout_seconds=0.2,
            queue_high_watermark_bytes=131072,
            queue_low_watermark_bytes=65536,
            queue_hard_cap_bytes=262144,
        )
    )
    await server.start()

    slow_reader, slow_writer = await asyncio.open_connection(
        "127.0.0.1", server.listening_port
    )
    fast_reader, fast_writer = await asyncio.open_connection(
        "127.0.0.1", server.listening_port
    )
    received_chunks: list[bytes] = []

    async def consume_fast_client() -> None:
        while True:
            data = await fast_reader.read(1024)
            if not data:
                break
            received_chunks.append(data)

    consumer_task = asyncio.create_task(consume_fast_client())

    try:
        payload = ("x" * 32768).encode("utf-8")
        started = time.perf_counter()
        for _ in range(TM_INT_03_BROADCAST_ITERATIONS):
            await server.broadcast(payload)
            for queued_bytes in server.queue_bytes_by_client().values():
                assert queued_bytes <= server.config.queue_hard_cap_bytes
            await asyncio.sleep(0)

        broadcast_elapsed = time.perf_counter() - started
        assert broadcast_elapsed <= TM_INT_03_MAX_BROADCAST_SECONDS

        disconnected = False
        disconnect_deadline = (
            time.monotonic() + server.config.slow_client_timeout_seconds + 2.0
        )
        while time.monotonic() < disconnect_deadline:
            disconnected = any(
                event.get("event") == "client_disconnect"
                and event.get("reason") != "server_stop"
                for event in server.events
            )
            if disconnected:
                break
            await asyncio.sleep(0.05)

        receive_deadline = time.monotonic() + 1.0
        while time.monotonic() < receive_deadline:
            if sum(len(chunk) for chunk in received_chunks) >= TM_INT_03_MIN_FAST_BYTES:
                break
            await asyncio.sleep(0.05)

        assert disconnected
        assert sum(len(chunk) for chunk in received_chunks) >= TM_INT_03_MIN_FAST_BYTES
    finally:
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)
        slow_writer.close()
        await slow_writer.wait_closed()
        fast_writer.close()
        await fast_writer.wait_closed()
        del slow_reader
        await server.stop()
        await server.stop()
