"""Asyncio UDP client sender."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(frozen=True)
class UdpClientConfig:
    host: str
    port: int
    local_host: str = "0.0.0.0"
    local_port: int = 0


class UdpClientSender:
    """UDP client that sends datagrams to a configured destination."""

    def __init__(self, config: UdpClientConfig) -> None:
        self.config = config
        self._transport: asyncio.DatagramTransport | None = None

    async def start(self) -> None:
        if self._transport is not None:
            return

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            asyncio.DatagramProtocol,
            local_addr=(self.config.local_host, self.config.local_port),
        )
        self._transport = transport

    async def stop(self) -> None:
        if self._transport is not None:
            self._transport.close()
            self._transport = None
        await asyncio.sleep(0)

    async def send(self, payload: bytes) -> None:
        if self._transport is None:
            raise RuntimeError("UDP client is not started")
        self._transport.sendto(payload, (self.config.host, self.config.port))
        await asyncio.sleep(0)
