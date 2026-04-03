"""Main tkinter application shell."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .config_panel import ConfigPanel
from .control_panel import ControlPanel
from .controller import SimulatorController
from .file_panel import FilePanel
from .log_panel import LogPanel
from .status_panel import StatusPanel


class App:
    """Functional tkinter UI that delegates runtime logic to the controller."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("TCP Server Simulator")
        self.controller: SimulatorController = SimulatorController()

        container = ttk.Frame(self.root, padding=8)
        container.pack(fill="both", expand=True)

        self.config_panel = ConfigPanel(container)
        self.config_panel.pack(fill="x", pady=4)

        self.file_panel = FilePanel(container)
        self.file_panel.pack(fill="x", pady=4)

        self.control_panel = ControlPanel(container)
        self.control_panel.pack(fill="x", pady=4)

        self.status_panel = StatusPanel(container)
        self.status_panel.pack(fill="x", pady=4)

        self.log_panel = LogPanel(container)
        self.log_panel.pack(fill="both", expand=True, pady=4)

        self.control_panel.on_start = self._on_start
        self.control_panel.on_stop = self._on_stop
        self.control_panel.on_pause = self._on_pause
        self.control_panel.on_step = self._on_step
        self.control_panel.on_jump = self._on_jump
        self.control_panel.on_rate_change = self._on_rate_change
        self.control_panel.on_swap_file = self._on_swap_file
        self.control_panel.on_line_controls = self._on_line_controls

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._poll_controller_status)

    def run(self) -> None:
        self.root.mainloop()

    def _on_start(self) -> None:
        settings = self.config_panel.build_runtime_settings()
        self.controller.apply_settings(settings)
        self.status_panel.append_event("Start requested.")

    def _on_stop(self) -> None:
        self.controller.stop_transport()
        self.status_panel.append_event("Stop requested.")

    def _on_pause(self) -> None:
        self.status_panel.append_event(
            "Pause requested (scheduler wiring in next increment)."
        )

    def _on_step(self) -> None:
        self.status_panel.append_event(
            "Step requested (scheduler wiring in next increment)."
        )

    def _on_jump(self, line_number: int) -> None:
        self.status_panel.append_event(f"Jump requested to line {line_number}.")

    def _on_rate_change(self, rate: float) -> None:
        self.status_panel.update_rate(rate, 0.0)
        self.status_panel.append_event(f"Rate change requested: {rate} feat/s")

    def _on_swap_file(self, path: str) -> None:
        self.status_panel.append_event(f"File swap requested: {path}")

    def _on_line_controls(
        self,
        start_line: int | None,
        end_line: int | None,
        first_n: int | None,
    ) -> None:
        self.controller.set_line_controls(start_line, end_line, first_n)
        self.status_panel.append_event(
            "Line controls requested: "
            f"start={start_line}, end={end_line}, first_n={first_n}"
        )

    def _poll_controller_status(self) -> None:
        for message in self.controller.read_status_messages():
            self.status_panel.append_event(message)
        self.root.after(100, self._poll_controller_status)

    def _on_close(self) -> None:
        self.controller.shutdown()
        self.root.destroy()
