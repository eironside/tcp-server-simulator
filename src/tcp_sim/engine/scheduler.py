"""Send scheduler placeholder for Phase 3."""


class SendScheduler:
    """Placeholder scheduler for rate-controlled sending."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._running = False

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
