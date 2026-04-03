"""Mode/protocol/network configuration panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .controller import RuntimeSettings


class ConfigPanel(ttk.LabelFrame):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, text="Configuration")

        self.mode_var = tk.StringVar(value="server")
        self.protocol_var = tk.StringVar(value="tcp")
        self.host_var = tk.StringVar(value="127.0.0.1")
        self.port_var = tk.StringVar(value="5565")
        self.connect_timeout_var = tk.StringVar(value="10")
        self.send_timeout_var = tk.StringVar(value="10")
        self.reconnect_backoff_var = tk.StringVar(value="30")
        self.use_tls_var = tk.BooleanVar(value=False)
        self.tls_certfile_var = tk.StringVar(value="")
        self.tls_keyfile_var = tk.StringVar(value="")
        self.tls_ca_file_var = tk.StringVar(value="")
        self.tls_verify_var = tk.BooleanVar(value=True)
        self.tls_server_hostname_var = tk.StringVar(value="")

        ttk.Label(self, text="Mode").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Combobox(
            self,
            textvariable=self.mode_var,
            values=["server", "client"],
            state="readonly",
            width=10,
        ).grid(row=0, column=1, sticky="w", padx=4, pady=2)

        ttk.Label(self, text="Protocol").grid(
            row=0, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Combobox(
            self,
            textvariable=self.protocol_var,
            values=["tcp", "udp"],
            state="readonly",
            width=10,
        ).grid(row=0, column=3, sticky="w", padx=4, pady=2)

        ttk.Label(self, text="Host").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.host_var, width=16).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Port").grid(row=1, column=2, sticky="w", padx=4, pady=2)
        ttk.Entry(self, textvariable=self.port_var, width=10).grid(
            row=1, column=3, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Connect Timeout").grid(
            row=2, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.connect_timeout_var, width=10).grid(
            row=2, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Send Timeout").grid(
            row=2, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.send_timeout_var, width=10).grid(
            row=2, column=3, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="Reconnect Max Backoff").grid(
            row=3, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.reconnect_backoff_var, width=10).grid(
            row=3, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Checkbutton(self, text="Use TLS", variable=self.use_tls_var).grid(
            row=3, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Checkbutton(self, text="Verify TLS", variable=self.tls_verify_var).grid(
            row=3, column=3, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="TLS Cert File").grid(
            row=4, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.tls_certfile_var, width=16).grid(
            row=4, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="TLS Key File").grid(
            row=4, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.tls_keyfile_var, width=16).grid(
            row=4, column=3, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="TLS CA File").grid(
            row=5, column=0, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.tls_ca_file_var, width=16).grid(
            row=5, column=1, sticky="w", padx=4, pady=2
        )

        ttk.Label(self, text="TLS Server Hostname").grid(
            row=5, column=2, sticky="w", padx=4, pady=2
        )
        ttk.Entry(self, textvariable=self.tls_server_hostname_var, width=16).grid(
            row=5, column=3, sticky="w", padx=4, pady=2
        )

    def build_runtime_settings(self) -> RuntimeSettings:
        tls_certfile = self.tls_certfile_var.get().strip() or None
        tls_keyfile = self.tls_keyfile_var.get().strip() or None
        tls_ca_file = self.tls_ca_file_var.get().strip() or None
        tls_server_hostname = self.tls_server_hostname_var.get().strip() or None

        return RuntimeSettings(
            mode=self.mode_var.get().strip().lower(),
            protocol=self.protocol_var.get().strip().lower(),
            host=self.host_var.get().strip(),
            port=int(self.port_var.get().strip()),
            connect_timeout_seconds=float(self.connect_timeout_var.get().strip()),
            send_timeout_seconds=float(self.send_timeout_var.get().strip()),
            reconnect_max_backoff_seconds=float(
                self.reconnect_backoff_var.get().strip()
            ),
            use_tls=self.use_tls_var.get(),
            tls_certfile=tls_certfile,
            tls_keyfile=tls_keyfile,
            tls_ca_file=tls_ca_file,
            tls_verify=self.tls_verify_var.get(),
            tls_server_hostname=tls_server_hostname,
        )
