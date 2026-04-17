"""Shared transport primitives used by sender and receiver transports."""

from __future__ import annotations

from typing import Callable

EventCallback = Callable[[dict[str, object]], None]


class EventEmitter:
    """Mixin that provides an append-only event log plus optional callback fan-out.

    Subclasses must call :meth:`_init_events` during ``__init__`` before any
    call to :meth:`_emit_event`.
    """

    events: list[dict[str, object]]
    _on_event: EventCallback | None

    def _init_events(self, on_event: EventCallback | None) -> None:
        self.events = []
        self._on_event = on_event

    def _emit_event(self, event: str, **payload: object) -> None:
        record: dict[str, object] = {"event": event, **payload}
        self.events.append(record)
        if self._on_event is not None:
            self._on_event(record)


class ReconnectBackoff:
    """Exponential backoff helper shared by client-mode transports.

    Starts at ``initial_seconds`` and doubles on each :meth:`advance` call up
    to ``max_seconds``. Call :meth:`reset` on successful connect.
    """

    def __init__(
        self,
        initial_seconds: float = 1.0,
        max_seconds: float = 30.0,
    ) -> None:
        if initial_seconds <= 0:
            raise ValueError("initial_seconds must be > 0")
        if max_seconds <= 0:
            raise ValueError("max_seconds must be > 0")
        # Clamp initial to max so callers can set an aggressive cap
        # (for tests) without worrying about the default initial value.
        self._initial = min(initial_seconds, max_seconds)
        self._max = max_seconds
        self._current = self._initial

    @property
    def current(self) -> float:
        return self._current

    def reset(self) -> None:
        self._current = self._initial

    def advance(self) -> float:
        """Return the current delay, then double it (capped at max)."""
        value = self._current
        self._current = min(self._current * 2, self._max)
        return value
