import pytest
import asyncio

from tcp_sim.transport.tcp_server import TcpServer, TcpServerConfig


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_server_reconnect_storm_lifecycle() -> None:
    server = TcpServer(TcpServerConfig(host="127.0.0.1", port=0))
    await server.start()

    try:
        for _ in range(30):
            reader, writer = await asyncio.open_connection("127.0.0.1", server.listening_port)
            writer.close()
            await writer.wait_closed()
            del reader

        await asyncio.sleep(0.1)
        assert server.connected_client_count == 0
        assert any(item["event"] == "client_connect" for item in server.events)
    finally:
        await server.stop()
