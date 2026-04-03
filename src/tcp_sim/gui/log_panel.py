"""On-demand JSON log load/refresh panel."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk


def load_log_lines(path: Path, max_lines: int = 2000) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return lines[-max_lines:]


def filter_log_lines(
    lines: list[str],
    level_filter: str = "ALL",
    search_text: str = "",
) -> list[str]:
    level = level_filter.strip().upper()
    query = search_text.strip().lower()

    filtered: list[str] = []
    for line in lines:
        if query and query not in line.lower():
            continue

        if level != "ALL":
            event_level = ""
            try:
                payload = json.loads(line)
                event_level = str(payload.get("level", "")).upper()
            except json.JSONDecodeError:
                event_level = ""

            if event_level != level:
                continue

        filtered.append(line)

    return filtered


def export_log_lines(lines: list[str], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text("\n".join(lines) + "\n", encoding="utf-8")


class LogPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Logs")
        self.log_path_var = tk.StringVar(value="tcp-sim.log")
        self.level_filter_var = tk.StringVar(value="ALL")
        self.search_var = tk.StringVar(value="")
        self._loaded_lines: list[str] = []
        self._filtered_lines: list[str] = []

        ttk.Label(self, text="Log File").grid(
            row=0, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.log_path_var, width=52).grid(
            row=0, column=1, sticky="ew", padx=4, pady=2
        )
        ttk.Button(self, text="Browse", command=self._browse).grid(
            row=0, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Button(self, text="Load", command=self.load).grid(
            row=1, column=1, sticky="e", padx=4, pady=2
        )
        ttk.Button(self, text="Refresh", command=self.load).grid(
            row=1, column=2, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Level").grid(row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(
            self,
            textvariable=self.level_filter_var,
            values=["ALL", "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
            state="readonly",
            width=10,
        ).grid(row=2, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(self, text="Search").grid(row=2, column=2, sticky="e", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.search_var, width=24).grid(
            row=2, column=3, sticky="ew", padx=4, pady=2
        )

        ttk.Button(self, text="Apply Filter", command=self.apply_filters).grid(
            row=3, column=1, sticky="e", padx=4, pady=2
        )
        ttk.Button(self, text="Export", command=self.export_filtered).grid(
            row=3, column=2, sticky="w", padx=4, pady=2
        )

        self.text = tk.Text(self, height=10, width=84)
        self.text.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)

    def _browse(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select log file",
            filetypes=[("Log files", "*.log *.json"), ("All files", "*.*")],
        )
        if selected:
            self.log_path_var.set(selected)

    def load(self) -> None:
        path = Path(self.log_path_var.get().strip())
        if not path.exists():
            self._loaded_lines = []
            self._filtered_lines = []
            self.text.delete("1.0", tk.END)
            self.text.insert(tk.END, f"Log file not found: {path}\n")
            return

        self._loaded_lines = load_log_lines(path)
        self.apply_filters()

    def apply_filters(self) -> None:
        self.text.delete("1.0", tk.END)
        self._filtered_lines = filter_log_lines(
            self._loaded_lines,
            level_filter=self.level_filter_var.get(),
            search_text=self.search_var.get(),
        )
        for line in self._filtered_lines:
            self.text.insert(tk.END, line + "\n")

    def export_filtered(self) -> None:
        if not self._filtered_lines:
            self.text.insert(tk.END, "No filtered lines to export.\n")
            return

        destination = filedialog.asksaveasfilename(
            title="Export filtered log entries",
            defaultextension=".log",
            filetypes=[("Log files", "*.log"), ("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not destination:
            return

        export_log_lines(self._filtered_lines, Path(destination))
        self.text.insert(tk.END, f"Exported {len(self._filtered_lines)} lines to {destination}\n")
