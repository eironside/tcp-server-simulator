"""Transport control widgets."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class ControlPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Transport Controls")

        self.rate_var = tk.StringVar(value="10")
        self.loop_var = tk.BooleanVar(value=True)
        self.jump_line_var = tk.StringVar(value="1")
        self.swap_file_var = tk.StringVar(value="")

        self.on_start: Callable[[], None] | None = None
        self.on_stop: Callable[[], None] | None = None
        self.on_pause: Callable[[], None] | None = None
        self.on_step: Callable[[], None] | None = None
        self.on_jump: Callable[[int], None] | None = None
        self.on_rate_change: Callable[[float], None] | None = None
        self.on_swap_file: Callable[[str], None] | None = None

        ttk.Label(self, text="Rate (feat/s)").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.rate_var, width=8).grid(row=0, column=1, sticky="w", padx=4, pady=2)
        ttk.Button(self, text="Apply Rate", command=self._rate_clicked).grid(row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(self, text="Loop", variable=self.loop_var).grid(row=0, column=3, sticky="w", padx=4, pady=2)

        ttk.Button(self, text="Start", command=self._start_clicked).grid(row=1, column=0, padx=4, pady=4)
        ttk.Button(self, text="Pause", command=self._pause_clicked).grid(row=1, column=1, padx=4, pady=4)
        ttk.Button(self, text="Stop", command=self._stop_clicked).grid(row=1, column=2, padx=4, pady=4)
        ttk.Button(self, text="Step", command=self._step_clicked).grid(row=1, column=3, padx=4, pady=4)

        ttk.Label(self, text="Jump to Line").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.jump_line_var, width=8).grid(row=2, column=1, sticky="w", padx=4, pady=2)
        ttk.Button(self, text="Jump", command=self._jump_clicked).grid(row=2, column=2, sticky="w", padx=4, pady=2)

        ttk.Label(self, text="Swap File").grid(row=3, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.swap_file_var, width=36).grid(row=3, column=1, columnspan=2, sticky="ew", padx=4, pady=2)
        ttk.Button(self, text="Apply Swap", command=self._swap_clicked).grid(row=3, column=3, sticky="w", padx=4, pady=2)

    def _start_clicked(self) -> None:
        if self.on_start is not None:
            self.on_start()

    def _stop_clicked(self) -> None:
        if self.on_stop is not None:
            self.on_stop()

    def _pause_clicked(self) -> None:
        if self.on_pause is not None:
            self.on_pause()

    def _step_clicked(self) -> None:
        if self.on_step is not None:
            self.on_step()

    def _jump_clicked(self) -> None:
        if self.on_jump is not None:
            self.on_jump(int(self.jump_line_var.get().strip()))

    def _rate_clicked(self) -> None:
        if self.on_rate_change is not None:
            self.on_rate_change(float(self.rate_var.get().strip()))

    def _swap_clicked(self) -> None:
        if self.on_swap_file is not None:
            self.on_swap_file(self.swap_file_var.get().strip())
