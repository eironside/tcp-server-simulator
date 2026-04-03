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
        self._source_records: list[bytes] = list(records or [])
        self._records: list[bytes] = list(self._source_records)
        self._rate_features_per_second = max(rate_features_per_second, 0.1)
        self._loop = loop
        self._start_line: int | None = None
        self._end_line: int | None = None
        self._first_n: int | None = None

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
    def start_line(self) -> int | None:
        return self._start_line

    @property
    def end_line(self) -> int | None:
        return self._end_line

    @property
    def first_n(self) -> int | None:
        return self._first_n

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
        self._source_records = list(records)
        self._rebuild_active_records()

    def request_file_swap(
        self,
        records: Sequence[bytes],
        header_payload: bytes | None = None,
    ) -> None:
        self._pending_swap = (list(records), header_payload)

    def set_line_controls(
        self,
        start_line: int | None = None,
        end_line: int | None = None,
        first_n: int | None = None,
    ) -> None:
        if start_line is not None and start_line < 1:
            raise ValueError("start_line must be >= 1")
        if end_line is not None and end_line < 1:
            raise ValueError("end_line must be >= 1")
        if first_n is not None and first_n < 1:
            raise ValueError("first_n must be >= 1")
        if (
            start_line is not None
            and end_line is not None
            and end_line < start_line
        ):
            raise ValueError("end_line must be >= start_line")

        self._start_line = start_line
        self._end_line = end_line
        self._first_n = first_n
        self._rebuild_active_records()

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

        self._source_records = records
        self._rebuild_active_records()
        self._generation += 1
        self._pending_header = header_payload

    def _rebuild_active_records(self) -> None:
        records = list(self._source_records)

        start_idx = (self._start_line - 1) if self._start_line is not None else 0
        end_idx = self._end_line if self._end_line is not None else len(records)

        if start_idx >= len(records):
            filtered: list[bytes] = []
        else:
            filtered = records[start_idx:end_idx]

        if self._first_n is not None:
            filtered = filtered[: self._first_n]

        self._records = filtered
        self._cursor = 0
