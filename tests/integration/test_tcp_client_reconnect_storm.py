import pytest
import asyncio
import socket

from tcp_sim.transport.tcp_client import TcpClient, TcpClientConfig


def _reserve_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_client_reconnects_after_flap() -> None:
    async def handler(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await asyncio.sleep(10)
        finally:
            writer.close()

    port = _reserve_port()
    server: asyncio.AbstractServer | None = None

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
        await asyncio.sleep(0.8)
        server = await asyncio.start_server(handler, host="127.0.0.1", port=port)
        await asyncio.wait_for(client.connected_event.wait(), timeout=2.5)
        assert client.reconnect_count >= 1
    finally:
        try:
            await asyncio.wait_for(client.stop(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        if server is not None:
            server.close()
            try:
                await asyncio.wait_for(server.wait_closed(), timeout=2.0)
            except asyncio.TimeoutError:
                pass
