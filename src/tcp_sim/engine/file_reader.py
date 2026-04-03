"""Streaming file reader placeholder for Phase 1."""


class FileReader:
    """Placeholder class for the streaming CSV reader."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._ready = False

    def initialize(self) -> None:
        self._ready = True

    @property
    def is_ready(self) -> bool:
        return self._ready
