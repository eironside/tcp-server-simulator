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
        self._expanded = False
        self._last_notice: str | None = None
        self._modal_window: tk.Toplevel | None = None
        self._modal_text: tk.Text | None = None
        self._modal_geometry: str | None = None
        self._modal_was_zoomed = False

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
        self.expand_button = ttk.Button(
            self,
            text="Expand",
            command=self.toggle_expand,
        )
        self.expand_button.grid(row=1, column=3, sticky="e", padx=4, pady=2)
        ttk.Button(self, text="Pop Out", command=self.open_modal).grid(
            row=0, column=3, sticky="e", padx=4, pady=2
        )

        self.level_label = ttk.Label(self, text="Level")
        self.level_label.grid(row=2, column=0, sticky="w", padx=4, pady=2)
        self.level_combo = ttk.Combobox(
            self,
            textvariable=self.level_filter_var,
            values=["ALL", "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
            state="readonly",
            width=10,
        )
        self.level_combo.grid(row=2, column=1, sticky="w", padx=4, pady=2)

        self.search_label = ttk.Label(self, text="Search")
        self.search_label.grid(row=2, column=2, sticky="e", padx=4, pady=2)
        self.search_entry = ttk.Entry(self, textvariable=self.search_var, width=24)
        self.search_entry.grid(row=2, column=3, sticky="ew", padx=4, pady=2)

        self.apply_button = ttk.Button(
            self,
            text="Apply Filter",
            command=self.apply_filters,
        )
        self.apply_button.grid(row=3, column=1, sticky="e", padx=4, pady=2)
        self.export_button = ttk.Button(
            self,
            text="Export",
            command=self.export_filtered,
        )
        self.export_button.grid(row=3, column=2, sticky="w", padx=4, pady=2)

        self.text = tk.Text(self, height=10, width=84)
        self.text.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)

        self._expandable_widgets: list[tk.Widget] = [
            self.level_label,
            self.level_combo,
            self.search_label,
            self.search_entry,
            self.apply_button,
            self.export_button,
            self.text,
        ]
        self._set_expanded(False)

    def toggle_expand(self) -> None:
        self._set_expanded(not self._expanded)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        if expanded:
            for widget in self._expandable_widgets:
                widget.grid()
            self.expand_button.configure(text="Collapse")
            return

        for widget in self._expandable_widgets:
            widget.grid_remove()
        self.expand_button.configure(text="Expand")

    def open_modal(self) -> None:
        if self._modal_window is not None and self._modal_window.winfo_exists():
            self._modal_window.deiconify()
            self._modal_window.lift()
            self._modal_window.focus_force()
            return

        parent = self.winfo_toplevel()
        window = tk.Toplevel(parent)
        window.title("Logs")
        window.transient(parent)
        window.grab_set()
        window.minsize(800, 380)
        window.rowconfigure(2, weight=1)
        window.columnconfigure(1, weight=1)

        ttk.Label(window, text="Log File").grid(
            row=0, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Entry(window, textvariable=self.log_path_var, width=70).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=6, pady=4
        )
        ttk.Button(window, text="Browse", command=self._browse).grid(
            row=0, column=3, sticky="w", padx=6, pady=4
        )
        ttk.Button(window, text="Refresh", command=self.load).grid(
            row=0, column=4, sticky="w", padx=6, pady=4
        )
        ttk.Button(window, text="Close", command=self._close_modal).grid(
            row=0, column=5, sticky="e", padx=6, pady=4
        )

        ttk.Label(window, text="Level").grid(
            row=1, column=0, sticky="w", padx=6, pady=4
        )
        ttk.Combobox(
            window,
            textvariable=self.level_filter_var,
            values=["ALL", "DEBUG", "INFO", "WARN", "ERROR", "CRITICAL"],
            state="readonly",
            width=10,
        ).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(window, text="Search").grid(
            row=1, column=2, sticky="e", padx=6, pady=4
        )
        ttk.Entry(window, textvariable=self.search_var, width=28).grid(
            row=1, column=3, sticky="ew", padx=6, pady=4
        )
        ttk.Button(window, text="Apply Filter", command=self.apply_filters).grid(
            row=1, column=4, sticky="e", padx=6, pady=4
        )
        ttk.Button(window, text="Export", command=self.export_filtered).grid(
            row=1, column=5, sticky="w", padx=6, pady=4
        )

        text_frame = ttk.Frame(window)
        text_frame.grid(
            row=2,
            column=0,
            columnspan=6,
            sticky="nsew",
            padx=6,
            pady=(2, 6),
        )
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)

        modal_text = tk.Text(text_frame, height=20, width=120)
        modal_text.grid(row=0, column=0, sticky="nsew")
        modal_scroll = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=modal_text.yview,
        )
        modal_scroll.grid(row=0, column=1, sticky="ns")
        modal_text.configure(yscrollcommand=modal_scroll.set)

        self._modal_window = window
        self._modal_text = modal_text
        if self._modal_geometry:
            window.geometry(self._modal_geometry)
        if self._modal_was_zoomed:
            try:
                window.state("zoomed")
            except tk.TclError:
                pass

        window.bind("<Configure>", self._on_modal_configure)
        window.protocol("WM_DELETE_WINDOW", self._close_modal)
        self._write_to_text_widget(
            modal_text,
            self._filtered_lines,
            self._last_notice,
        )

    def _on_modal_configure(self, _event) -> None:
        if self._modal_window is None or not self._modal_window.winfo_exists():
            return

        try:
            state = self._modal_window.state()
            self._modal_was_zoomed = state == "zoomed"
            if state == "normal":
                self._modal_geometry = self._modal_window.geometry()
        except tk.TclError:
            return

    def _close_modal(self) -> None:
        if self._modal_window is None:
            return

        if self._modal_window.winfo_exists():
            self._on_modal_configure(None)
            try:
                self._modal_window.grab_release()
            except tk.TclError:
                pass
            self._modal_window.destroy()

        self._modal_window = None
        self._modal_text = None

    @staticmethod
    def _write_to_text_widget(
        widget: tk.Text,
        lines: list[str],
        notice: str | None,
    ) -> None:
        widget.delete("1.0", tk.END)
        if lines:
            for line in lines:
                widget.insert(tk.END, line + "\n")
            widget.see(tk.END)
            return

        if notice:
            widget.insert(tk.END, notice + "\n")

    def _render_text_views(self, lines: list[str], notice: str | None) -> None:
        self._last_notice = notice
        self._write_to_text_widget(self.text, lines, notice)
        if self._modal_text is not None and self._modal_text.winfo_exists():
            self._write_to_text_widget(self._modal_text, lines, notice)

    def _append_feedback(self, message: str) -> None:
        self.text.insert(tk.END, message + "\n")
        self.text.see(tk.END)
        if self._modal_text is not None and self._modal_text.winfo_exists():
            self._modal_text.insert(tk.END, message + "\n")
            self._modal_text.see(tk.END)

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
            self._render_text_views([], f"Log file not found: {path}")
            return

        self._loaded_lines = load_log_lines(path)
        self.apply_filters()

    def apply_filters(self) -> None:
        self._filtered_lines = filter_log_lines(
            self._loaded_lines,
            level_filter=self.level_filter_var.get(),
            search_text=self.search_var.get(),
        )

        notice: str | None = None
        if not self._loaded_lines:
            notice = "No log entries loaded."
        elif not self._filtered_lines:
            notice = "No log entries match current filters."

        self._render_text_views(self._filtered_lines, notice)

    def export_filtered(self) -> None:
        if not self._filtered_lines:
            self._append_feedback("No filtered lines to export.")
            return

        destination = filedialog.asksaveasfilename(
            title="Export filtered log entries",
            defaultextension=".log",
            filetypes=[
                ("Log files", "*.log"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not destination:
            return

        export_log_lines(self._filtered_lines, Path(destination))
        self._append_feedback(
            f"Exported {len(self._filtered_lines)} lines to {destination}"
        )
