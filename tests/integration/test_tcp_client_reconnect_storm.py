import asyncio
import socket
import time
from contextlib import suppress

import pytest

from tcp_sim.transport.tcp_client_sender import TcpClient, TcpClientConfig
from tests.scenario_thresholds import (
    TM_INT_02_FLAP_CYCLES,
    TM_INT_02_MAX_RECOVERY_SECONDS,
    TM_INT_02_MIN_RECONNECT_EVENTS,
)


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_client_reconnects_after_flap() -> None:
    received_lines: list[bytes] = []
    line_received_event = asyncio.Event()
    active_writers: list[asyncio.StreamWriter] = []

    async def handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        active_writers.append(writer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                received_lines.append(line)
                line_received_event.set()
        finally:
            writer.close()
            with suppress(OSError, RuntimeError):
                await writer.wait_closed()
            with suppress(ValueError):
                active_writers.remove(writer)

    async def wait_for_received(
        target_count: int, timeout_seconds: float = 1.5
    ) -> None:
        while len(received_lines) < target_count:
            line_received_event.clear()
            await asyncio.wait_for(line_received_event.wait(), timeout=timeout_seconds)

    async def run_flap_cycle(
        cycle: int,
        client: TcpClient,
        port: int,
    ) -> float:
        client.connected_event.clear()
        cycle_server = await asyncio.start_server(handler, host="127.0.0.1", port=port)
        cycle_started = time.perf_counter()
        await asyncio.wait_for(
            client.connected_event.wait(), timeout=TM_INT_02_MAX_RECOVERY_SECONDS + 1.0
        )
        recovery_time = time.perf_counter() - cycle_started

        await client.send(f"{cycle},ok\n".encode("utf-8"))
        await wait_for_received(cycle + 1)

        for writer in list(active_writers):
            writer.close()
            with suppress(OSError, RuntimeError):
                await writer.wait_closed()

        cycle_server.close()
        await cycle_server.wait_closed()
        await asyncio.sleep(0.25)
        return recovery_time

    port = _reserve_port()
    recovery_times: list[float] = []

    client = TcpClient(
        TcpClientConfig(
            host="127.0.0.1",
            port=port,
            connect_timeout_seconds=0.2,
            send_timeout_seconds=1.0,
            reconnect_max_backoff_seconds=0.5,
        )
    )

    await client.start()

    try:
        for cycle in range(TM_INT_02_FLAP_CYCLES):
            recovery_times.append(await run_flap_cycle(cycle, client, port))

        assert client.reconnect_count >= TM_INT_02_MIN_RECONNECT_EVENTS
        assert max(recovery_times) <= TM_INT_02_MAX_RECOVERY_SECONDS
        assert all(line.endswith(b"\n") for line in received_lines)

        decoded = {line.decode("utf-8").strip() for line in received_lines}
        for cycle in range(TM_INT_02_FLAP_CYCLES):
            assert f"{cycle},ok" in decoded
    finally:
        try:
            await asyncio.wait_for(client.stop(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
            pass
