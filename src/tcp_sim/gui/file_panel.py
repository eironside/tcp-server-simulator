"""File selection and preview panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, ttk

from tcp_sim.engine.file_reader import FileReader


class FilePanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="File")
        self.file_var = tk.StringVar(value="")
        self.delimiter_var = tk.StringVar(value=",")
        self.has_header_var = tk.BooleanVar(value=True)

        ttk.Label(self, text="Path").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.file_var, width=52).grid(
            row=0, column=1, sticky="ew", padx=4, pady=2
        )
        ttk.Button(self, text="Browse", command=self._browse_file).grid(
            row=0, column=2, sticky="w", padx=4, pady=2
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

        self.preview = tk.Text(self, height=8, width=84)
        self.preview.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=4, pady=4)

        ttk.Button(self, text="Preview", command=self.load_preview).grid(
            row=3, column=2, sticky="e", padx=4, pady=4
        )

    def _browse_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select data file",
            filetypes=[("Delimited files", "*.csv *.txt *.tsv"), ("All files", "*.*")],
        )
        if selected:
            self.file_var.set(selected)

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
