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
        try:
            settings = self.config_panel.build_runtime_settings()
            stream_settings = self.file_panel.build_stream_settings(
                rate_features_per_second=self.control_panel.get_rate(),
                loop=self.control_panel.get_loop(),
            )
        except ValueError as exc:
            self.status_panel.append_event(f"Invalid start configuration: {exc}")
            return

        self.controller.start_transmission(settings, stream_settings)
        self.status_panel.update_rate(stream_settings.rate_features_per_second, 0.0)
        self.status_panel.append_event("Start requested.")

    def _on_stop(self) -> None:
        self.controller.stop_transport()
        self.status_panel.append_event("Stop requested.")

    def _on_pause(self) -> None:
        self.controller.toggle_pause()
        self.status_panel.append_event("Pause/resume requested.")

    def _on_step(self) -> None:
        self.controller.step_once()
        self.status_panel.append_event("Step requested.")

    def _on_jump(self, line_number: int) -> None:
        self.controller.jump_to(line_number)
        self.status_panel.append_event(f"Jump requested to line {line_number}.")

    def _on_rate_change(self, rate: float) -> None:
        self.controller.update_rate(rate)
        self.status_panel.update_rate(rate, 0.0)
        self.status_panel.append_event(f"Rate change requested: {rate} feat/s")

    def _on_swap_file(self, path: str) -> None:
        if not path.strip():
            self.status_panel.append_event("File swap requested with empty path.")
            return

        self.file_panel.file_var.set(path)
        self.controller.swap_file(
            file_path=path,
            delimiter=self.file_panel.delimiter_var.get() or ",",
            has_header=self.file_panel.has_header_var.get(),
            send_header=self.file_panel.send_header_var.get(),
            strip_lf=self.file_panel.strip_lf_var.get(),
            strip_cr=self.file_panel.strip_cr_var.get(),
        )
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
            if not self._handle_status_message(message):
                self.status_panel.append_event(message)
        self.root.after(100, self._poll_controller_status)

    def _handle_status_message(self, message: str) -> bool:
        handlers = (
            ("__connections__:", self._handle_connection_status),
            ("__progress__:", self._handle_progress_status),
            ("__rate__:", self._handle_rate_status),
            ("__sent__:", self._handle_sent_status),
        )

        for prefix, handler in handlers:
            if message.startswith(prefix):
                handler(message)
                return True

        return False

    def _handle_connection_status(self, message: str) -> None:
        _, _, raw_count = message.partition(":")
        try:
            self.status_panel.update_connections(int(raw_count))
        except ValueError:
            self.status_panel.append_event(message)

    def _handle_progress_status(self, message: str) -> None:
        _, _, payload = message.partition(":")
        current_raw, _, total_raw = payload.partition(":")
        try:
            self.status_panel.update_progress(int(current_raw), int(total_raw))
        except ValueError:
            self.status_panel.append_event(message)

    def _handle_rate_status(self, message: str) -> None:
        _, _, payload = message.partition(":")
        feat_raw, _, kb_raw = payload.partition(":")
        try:
            self.status_panel.update_rate(float(feat_raw), float(kb_raw))
        except ValueError:
            self.status_panel.append_event(message)

    def _handle_sent_status(self, message: str) -> None:
        _, _, payload = message.partition(":")
        lines_raw, _, bytes_raw = payload.partition(":")

        try:
            lines_sent = int(lines_raw)
            bytes_sent = int(bytes_raw)
        except ValueError:
            self.status_panel.append_event(message)
            return

        update_sent = getattr(self.status_panel, "update_sent_totals", None)
        if callable(update_sent):
            update_sent(lines_sent, bytes_sent)
            return

        self.status_panel.append_event(
            f"Sent totals: {lines_sent} lines | {bytes_sent} bytes"
        )

    def _on_close(self) -> None:
        self.controller.shutdown()
        self.root.destroy()
