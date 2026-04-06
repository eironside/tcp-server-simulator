"""File selection and preview panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from tcp_sim.engine.file_reader import FileReader

from .controller import StreamSettings


class FilePanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="File")
        self.file_var = tk.StringVar(value="")
        self.delimiter_var = tk.StringVar(value=",")
        self.has_header_var = tk.BooleanVar(value=True)
        self.send_header_var = tk.BooleanVar(value=True)
        self.strip_lf_var = tk.BooleanVar(value=False)
        self.strip_cr_var = tk.BooleanVar(value=False)
        self.velocity_compatibility_var = tk.BooleanVar(value=False)

        ttk.Label(self, text="Path").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.file_var, width=52).grid(
            row=0, column=1, sticky="ew", padx=4, pady=2
        )
        ttk.Button(self, text="Browse", command=self._browse_file).grid(
            row=0, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Button(self, text="Refresh", command=self.load_preview).grid(
            row=0, column=3, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Delimiter").grid(
            row=1, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.delimiter_var, width=4).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )
        ttk.Checkbutton(self, text="Header Row", variable=self.has_header_var).grid(
            row=1, column=2, sticky="w", padx=4, pady=2
        )
        self.send_header_check = ttk.Checkbutton(
            self,
            text="Send Header",
            variable=self.send_header_var,
        )
        self.send_header_check.grid(row=1, column=3, sticky="w", padx=4, pady=2)

        self.strip_lf_check = ttk.Checkbutton(
            self,
            text="Strip LF (\\n)",
            variable=self.strip_lf_var,
        )
        self.strip_lf_check.grid(row=2, column=0, sticky="w", padx=4, pady=2)

        ttk.Checkbutton(
            self,
            text="Strip CR (\\r)",
            variable=self.strip_cr_var,
        ).grid(row=2, column=1, sticky="w", padx=4, pady=2)

        ttk.Checkbutton(
            self,
            text="Velocity Delimited Sampling Compatibility",
            variable=self.velocity_compatibility_var,
            command=self._on_velocity_compatibility_toggled,
        ).grid(row=2, column=2, columnspan=2, sticky="w", padx=4, pady=2)

        self.preview = tk.Text(self, height=8, width=84)
        self.preview.grid(row=3, column=0, columnspan=4, sticky="nsew", padx=4, pady=4)

    def _on_velocity_compatibility_toggled(self) -> None:
        enabled = self.velocity_compatibility_var.get()

        if enabled:
            self.send_header_var.set(False)
            self.strip_lf_var.set(False)
            self.send_header_check.state(["disabled"])
            self.strip_lf_check.state(["disabled"])
            return

        self.send_header_check.state(["!disabled"])
        self.strip_lf_check.state(["!disabled"])

    def _browse_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select data file",
            filetypes=[
                (
                    "Supported data files",
                    "*.csv *.txt *.tsv *.json *.jsonl *.xml",
                ),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.file_var.set(selected)
            self.load_preview()

    def load_preview(self) -> None:
        self.preview.delete("1.0", tk.END)
        path = self.file_var.get().strip()
        if not path:
            return

        reader = FileReader(
            file_path=path,
            delimiter=self.delimiter_var.get() or ",",
            has_header=self.has_header_var.get(),
        )
        rows = reader.load_preview(limit=10)
        for item in rows:
            validity = "VALID" if item.valid else "INVALID"
            self.preview.insert(
                tk.END, f"[{validity}] row={item.raw_row_number} {item.fields}\n"
            )

    def build_stream_settings(
        self,
        rate_features_per_second: float,
        loop: bool,
        line_ending: str = "\n",
    ) -> StreamSettings:
        return StreamSettings(
            file_path=self.file_var.get().strip(),
            delimiter=self.delimiter_var.get() or ",",
            has_header=self.has_header_var.get(),
            send_header=self.send_header_var.get(),
            rate_features_per_second=rate_features_per_second,
            loop=loop,
            line_ending=line_ending,
            strip_lf=self.strip_lf_var.get(),
            strip_cr=self.strip_cr_var.get(),
            velocity_compatibility_mode=self.velocity_compatibility_var.get(),
        )
