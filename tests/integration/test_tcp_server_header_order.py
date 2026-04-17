import asyncio

import pytest

from tcp_sim.transport.tcp_server_sender import TcpServerConfig, TcpServerSender


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tcp_server_sends_header_before_broadcast_to_new_client() -> None:
    header = b"id,lat,lon,timestamp\n"
    payload = b"truck-01,34.0,-118.2,2026-04-03T10:00:00Z\n"

    server = TcpServerSender(
        TcpServerConfig(
            host="127.0.0.1",
            port=0,
            send_header_on_connect=True,
            header_payload=header,
        )
    )
    await server.start()

    sender_task: asyncio.Task[None] | None = None
    try:

        async def sender() -> None:
            while True:
                await server.broadcast(payload)
                await asyncio.sleep(0.01)

        sender_task = asyncio.create_task(sender())

        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.listening_port
        )
        try:
            first_line = await asyncio.wait_for(reader.readline(), timeout=1.5)
            second_line = await asyncio.wait_for(reader.readline(), timeout=1.5)
        finally:
            writer.close()
            await writer.wait_closed()

        assert first_line == header
        assert second_line == payload
    finally:
        if sender_task is not None:
            sender_task.cancel()
            await asyncio.gather(sender_task, return_exceptions=True)
        await server.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_wait_for_broadcast_clients_unblocks_on_connect() -> None:
    server = TcpServerSender(
        TcpServerConfig(
            host="127.0.0.1",
            port=0,
            send_header_on_connect=True,
            header_payload=b"id,value\n",
        )
    )
    await server.start()

    waiter = asyncio.create_task(server.wait_for_broadcast_clients())
    try:
        await asyncio.sleep(0.05)
        assert not waiter.done()

        reader, writer = await asyncio.open_connection(
            "127.0.0.1", server.listening_port
        )
        try:
            await asyncio.wait_for(waiter, timeout=1.0)
            assert waiter.done()
            assert server.has_broadcast_clients()
        finally:
            writer.close()
            await writer.wait_closed()
            del reader
    finally:
        await server.stop()
