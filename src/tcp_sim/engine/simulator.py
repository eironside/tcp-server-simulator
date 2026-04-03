"""Simulator orchestration placeholder."""


class SimulatorEngine:
    """Placeholder orchestrator for engine and transport wiring."""

    def __init__(self, *_args, **_kwargs) -> None:
        self._started = False

    def start(self) -> None:
        self._started = True

    def stop(self) -> None:
        self._started = False
