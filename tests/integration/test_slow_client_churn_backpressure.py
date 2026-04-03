import pytest
import asyncio

from tcp_sim.transport.tcp_server import TcpServer, TcpServerConfig


@pytest.mark.integration
@pytest.mark.asyncio
async def test_slow_client_is_disconnected_without_global_stall() -> None:
    server = TcpServer(
        TcpServerConfig(
            host="127.0.0.1",
            port=0,
            send_timeout_seconds=0.2,
            slow_client_timeout_seconds=0.2,
            queue_high_watermark_bytes=131072,
            queue_low_watermark_bytes=65536,
            queue_hard_cap_bytes=262144,
        )
    )
    await server.start()

    slow_reader, slow_writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    fast_reader, fast_writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
    received_chunks: list[bytes] = []

    async def consume_fast_client() -> None:
        while True:
            data = await fast_reader.read(1024)
            if not data:
                break
            received_chunks.append(data)

    consumer_task = asyncio.create_task(consume_fast_client())

    try:
        payload = ("x" * 65536).encode("utf-8")
        for _ in range(20):
            await server.broadcast(payload)

        await asyncio.sleep(1.0)

        assert received_chunks
        assert any(
            event.get("event") == "client_disconnect"
            and event.get("reason") != "server_stop"
            for event in server.events
        )
    finally:
        consumer_task.cancel()
        await asyncio.gather(consumer_task, return_exceptions=True)
        slow_writer.close()
        await slow_writer.wait_closed()
        fast_writer.close()
        await fast_writer.wait_closed()
        del slow_reader
        await server.stop()
