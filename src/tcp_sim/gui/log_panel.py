"""On-demand JSON log load/refresh panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk
from pathlib import Path


class LogPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Logs")
        self.log_path_var = tk.StringVar(value="tcp-sim.log")

        ttk.Label(self, text="Log File").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.log_path_var, width=52).grid(row=0, column=1, sticky="ew", padx=4, pady=2)
        ttk.Button(self, text="Browse", command=self._browse).grid(row=0, column=2, sticky="w", padx=4, pady=2)
        ttk.Button(self, text="Load", command=self.load).grid(row=1, column=1, sticky="e", padx=4, pady=2)
        ttk.Button(self, text="Refresh", command=self.load).grid(row=1, column=2, sticky="w", padx=4, pady=2)

        self.text = tk.Text(self, height=10, width=84)
        self.text.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select log file",
            filetypes=[("Log files", "*.log *.json"), ("All files", "*.*")],
        )
        if selected:
            self.log_path_var.set(selected)

    def load(self) -> None:
        self.text.delete("1.0", tk.END)
        path = Path(self.log_path_var.get().strip())
        if not path.exists():
            self.text.insert(tk.END, f"Log file not found: {path}\n")
            return

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line in lines[-500:]:
            self.text.insert(tk.END, line + "\n")
