"""Engine orchestrator for scheduler and transport callbacks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence

from .scheduler import ScheduledMessage, SendScheduler

SendCallback = Callable[[ScheduledMessage], Awaitable[None]]


@dataclass
class EngineStats:
    features_sent: int = 0
    bytes_sent: int = 0


class SimulatorEngine:
    """Compose scheduler and outbound transport callback."""

    def __init__(
        self,
        initial_records: Sequence[bytes] | None = None,
        send_callback: SendCallback | None = None,
        rate_features_per_second: float = 10.0,
        loop: bool = True,
    ) -> None:
        self.scheduler = SendScheduler(
            records=initial_records,
            rate_features_per_second=rate_features_per_second,
            loop=loop,
        )
        self._send_callback = send_callback
        self._run_task: asyncio.Task[None] | None = None
        self.stats = EngineStats()

    @property
    def is_running(self) -> bool:
        return self._run_task is not None and not self._run_task.done()

    async def start(self) -> None:
        if self.is_running:
            return
        if self._send_callback is None:
            raise RuntimeError("send_callback is not configured")

        self._run_task = asyncio.create_task(
            self.scheduler.run_auto(self._on_scheduled_message)
        )
        await asyncio.sleep(0)

    async def stop(self) -> None:
        self.scheduler.stop()
        if self._run_task is not None:
            self._run_task.cancel()
            await asyncio.gather(self._run_task, return_exceptions=True)
            self._run_task = None

    def pause(self) -> None:
        self.scheduler.pause()

    def resume(self) -> None:
        self.scheduler.resume()

    def step(self) -> ScheduledMessage | None:
        return self.scheduler.step()

    def jump_to(self, line_number: int) -> None:
        self.scheduler.jump_to(line_number)

    def update_rate(self, rate_features_per_second: float) -> None:
        self.scheduler.set_rate(rate_features_per_second)

    def set_line_controls(
        self,
        start_line: int | None = None,
        end_line: int | None = None,
        first_n: int | None = None,
    ) -> None:
        self.scheduler.set_line_controls(
            start_line=start_line,
            end_line=end_line,
            first_n=first_n,
        )

    def swap_records(
        self, new_records: Sequence[bytes], header_payload: bytes | None = None
    ) -> None:
        self.scheduler.request_file_swap(new_records, header_payload=header_payload)

    async def _on_scheduled_message(self, message: ScheduledMessage) -> None:
        assert self._send_callback is not None
        await self._send_callback(message)
        self.stats.features_sent += 1
        self.stats.bytes_sent += len(message.payload)
