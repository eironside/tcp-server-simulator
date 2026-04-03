"""Rate scheduler with step/auto/loop and runtime reconfiguration support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, Sequence


@dataclass(frozen=True)
class ScheduledMessage:
    payload: bytes
    generation: int
    is_header: bool
    line_number: int


class SendScheduler:
    """Generate outbound messages in step or automatic mode."""

    def __init__(
        self,
        records: Sequence[bytes] | None = None,
        rate_features_per_second: float = 10.0,
        loop: bool = True,
    ) -> None:
        self._records: list[bytes] = list(records or [])
        self._rate_features_per_second = max(rate_features_per_second, 0.1)
        self._loop = loop

        self._running = False
        self._paused = False
        self._cursor = 0
        self._generation = 0
        self._pending_header: bytes | None = None
        self._pending_swap: tuple[list[bytes], bytes | None] | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def current_line(self) -> int:
        return self._cursor + 1 if self._records else 0

    @property
    def total_lines(self) -> int:
        return len(self._records)

    @property
    def rate_features_per_second(self) -> float:
        return self._rate_features_per_second

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    def set_rate(self, rate_features_per_second: float) -> None:
        self._rate_features_per_second = max(rate_features_per_second, 0.1)

    def set_records(self, records: Sequence[bytes]) -> None:
        self._records = list(records)
        self._cursor = 0

    def request_file_swap(
        self,
        records: Sequence[bytes],
        header_payload: bytes | None = None,
    ) -> None:
        self._pending_swap = (list(records), header_payload)

    def jump_to(self, line_number: int) -> None:
        if line_number < 1 or line_number > len(self._records):
            raise ValueError("line_number out of range")
        self._cursor = line_number - 1

    def step(self) -> ScheduledMessage | None:
        self._apply_pending_swap_if_any()

        if self._pending_header is not None:
            header = self._pending_header
            self._pending_header = None
            return ScheduledMessage(
                payload=header,
                generation=self._generation,
                is_header=True,
                line_number=0,
            )

        if not self._records:
            return None

        if self._cursor >= len(self._records):
            if not self._loop:
                return None
            self._cursor = 0

        payload = self._records[self._cursor]
        line_number = self._cursor + 1
        self._cursor += 1

        return ScheduledMessage(
            payload=payload,
            generation=self._generation,
            is_header=False,
            line_number=line_number,
        )

    async def run_auto(
        self,
        send_callback: Callable[[ScheduledMessage], Awaitable[None]],
    ) -> None:
        self.start()
        try:
            while self._running:
                if self._paused:
                    await asyncio.sleep(0.05)
                    continue

                message = self.step()
                if message is None:
                    await asyncio.sleep(0.05)
                    continue

                await send_callback(message)
                await asyncio.sleep(1.0 / self._rate_features_per_second)
        finally:
            self.stop()

    def _apply_pending_swap_if_any(self) -> None:
        if self._pending_swap is None:
            return

        records, header_payload = self._pending_swap
        self._pending_swap = None

        self._records = records
        self._cursor = 0
        self._generation += 1
        self._pending_header = header_payload
