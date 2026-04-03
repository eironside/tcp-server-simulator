"""Status panel for runtime counters and event messages."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class StatusPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Status")

        self.connection_var = tk.StringVar(value="Connections: 0")
        self.progress_var = tk.StringVar(value="Line: 0 / 0")
        self.rate_var = tk.StringVar(value="Rate: 0.0 feat/s | 0.0 KB/s")
        self.sent_var = tk.StringVar(value="Sent: 0 lines | 0 bytes")

        ttk.Label(self, textvariable=self.connection_var).grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Label(self, textvariable=self.progress_var).grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Label(self, textvariable=self.rate_var).grid(
            row=2, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Label(self, textvariable=self.sent_var).grid(
            row=3, column=0, sticky="w", padx=4, pady=2
        )

        self.events = tk.Text(self, height=6, width=84)
        self.events.grid(row=4, column=0, sticky="nsew", padx=4, pady=4)

    def append_event(self, message: str) -> None:
        self.events.insert(tk.END, f"{message}\n")
        self.events.see(tk.END)

    def update_connections(self, count: int) -> None:
        self.connection_var.set(f"Connections: {count}")

    def update_progress(self, current_line: int, total_lines: int) -> None:
        self.progress_var.set(f"Line: {current_line} / {total_lines}")

    def update_rate(self, features_per_second: float, kb_per_second: float) -> None:
        self.rate_var.set(
            f"Rate: {features_per_second:.2f} feat/s | {kb_per_second:.2f} KB/s"
        )

    def update_sent_totals(self, lines_sent: int, bytes_sent: int) -> None:
        self.sent_var.set(f"Sent: {lines_sent} lines | {bytes_sent} bytes")
