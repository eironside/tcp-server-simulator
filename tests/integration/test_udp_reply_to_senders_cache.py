import asyncio
import socket

import pytest

from tcp_sim.transport.udp_server_sender import UdpServer, UdpServerConfig


@pytest.mark.integration
@pytest.mark.asyncio
async def test_udp_reply_to_senders_cache_limits_and_expiry() -> None:
    server = UdpServer(
        UdpServerConfig(
            host="127.0.0.1",
            port=0,
            recipient_mode="reply_to_senders",
            recipient_cache_ttl_seconds=0.4,
            recipient_cache_max_entries=3,
            recipient_cache_cleanup_interval_seconds=0.05,
        )
    )
    await server.start()

    senders: list[socket.socket] = []
    try:
        for _ in range(5):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(("127.0.0.1", 0))
            sock.settimeout(0.2)
            sock.sendto(b"hello", ("127.0.0.1", server.bound_port))
            senders.append(sock)

        await asyncio.sleep(0.1)
        assert server.recipient_count <= 3

        await server.send(b"reply")

        received = 0
        for sock in senders:
            try:
                data, _ = sock.recvfrom(1024)
                if data == b"reply":
                    received += 1
            except TimeoutError:
                pass

        assert received >= 1

        await asyncio.sleep(0.6)
        server.cleanup_expired()
        assert server.recipient_count == 0
    finally:
        for sock in senders:
            sock.close()
        await server.stop()
        await server.stop()
