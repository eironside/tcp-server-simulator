"""Connection and backpressure state tracking for TCP server mode."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QueueThresholds:
    high_watermark_bytes: int = 262144
    low_watermark_bytes: int = 131072
    hard_cap_bytes: int = 524288
    slow_client_timeout_seconds: float = 10.0


@dataclass
class ClientState:
    client_id: str
    writer: Any
    queued_payloads: list[bytes] = field(default_factory=list)
    queued_bytes: int = 0
    blocked: bool = False
    blocked_since: float | None = None


class ConnectionManager:
    """Maintain per-client queues and blocked/disconnect decisions."""

    def __init__(self, thresholds: QueueThresholds | None = None) -> None:
        self._thresholds = thresholds or QueueThresholds()
        self._clients: dict[str, ClientState] = {}

    @property
    def connected_clients(self) -> int:
        return len(self._clients)

    def register_client(self, client_id: str, writer: Any) -> ClientState:
        state = ClientState(client_id=client_id, writer=writer)
        self._clients[client_id] = state
        return state

    def unregister_client(self, client_id: str) -> None:
        self._clients.pop(client_id, None)

    def list_client_ids(self) -> list[str]:
        return list(self._clients)

    def get_client_state(self, client_id: str) -> ClientState | None:
        return self._clients.get(client_id)

    def enqueue_payload(
        self, client_id: str, payload: bytes
    ) -> tuple[bool, str | None]:
        state = self._clients.get(client_id)
        if state is None:
            return False, "client_not_found"

        next_bytes = state.queued_bytes + len(payload)
        if next_bytes > self._thresholds.hard_cap_bytes:
            return False, "hard_cap_exceeded"

        state.queued_payloads.append(payload)
        state.queued_bytes = next_bytes
        self._update_blocked_state(state)
        return True, None

    def pop_next_payload(self, client_id: str) -> bytes | None:
        state = self._clients.get(client_id)
        if state is None or not state.queued_payloads:
            return None

        payload = state.queued_payloads.pop(0)
        state.queued_bytes = max(0, state.queued_bytes - len(payload))
        self._update_blocked_state(state)
        return payload

    def get_disconnect_candidates(self, now: float | None = None) -> list[str]:
        current = now if now is not None else time.monotonic()
        candidates: list[str] = []

        for client_id, state in self._clients.items():
            if not state.blocked or state.blocked_since is None:
                continue
            blocked_duration = current - state.blocked_since
            if blocked_duration >= self._thresholds.slow_client_timeout_seconds:
                candidates.append(client_id)

        return candidates

    def blocked_clients(self) -> list[str]:
        return [
            client_id for client_id, state in self._clients.items() if state.blocked
        ]

    def _update_blocked_state(self, state: ClientState) -> None:
        if state.queued_bytes >= self._thresholds.high_watermark_bytes:
            if not state.blocked:
                state.blocked = True
                state.blocked_since = time.monotonic()
            return

        if state.queued_bytes <= self._thresholds.low_watermark_bytes:
            state.blocked = False
            state.blocked_since = None
