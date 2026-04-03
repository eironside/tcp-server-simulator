from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Iterable

REQUIRED_PYTHON = (3, 10)


@dataclass(frozen=True)
class PreflightCheckResult:
    name: str
    passed: bool
    details: str
    remediation: str = ""


def _check_python_version() -> PreflightCheckResult:
    current = sys.version_info[:3]
    if current >= REQUIRED_PYTHON:
        return PreflightCheckResult(
            name="python_version",
            passed=True,
            details=f"Python {current[0]}.{current[1]}.{current[2]} detected.",
        )

    return PreflightCheckResult(
        name="python_version",
        passed=False,
        details=(
            f"Python {current[0]}.{current[1]}.{current[2]} detected, "
            f"but {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]}+ is required."
        ),
        remediation="Install Python 3.10+ and re-run preflight.",
    )


def _check_virtual_environment() -> PreflightCheckResult:
    in_venv = (
        getattr(sys, "real_prefix", None) is not None
        or getattr(sys, "base_prefix", sys.prefix) != sys.prefix
        or bool(os.environ.get("VIRTUAL_ENV"))
    )

    if in_venv:
        return PreflightCheckResult(
            name="virtual_environment",
            passed=True,
            details="Active virtual environment detected.",
        )

    return PreflightCheckResult(
        name="virtual_environment",
        passed=False,
        details="No active virtual environment detected.",
        remediation=(
            "Create and activate a venv first. Example: " "python -m venv .venv"
        ),
    )


def _check_tkinter() -> PreflightCheckResult:
    try:
        import tkinter as tk
    except ImportError as exc:
        return PreflightCheckResult(
            name="tkinter",
            passed=False,
            details=f"Unable to import tkinter: {exc}",
            remediation=(
                "Install Tk support for Python, then re-run preflight. "
                "Linux often requires the python3-tk package."
            ),
        )

    try:
        interp = tk.Tcl()
        _ = interp.eval("info patchlevel")
    except (tk.TclError, OSError, RuntimeError) as exc:
        return PreflightCheckResult(
            name="tkinter",
            passed=False,
            details=f"tkinter imported but Tcl/Tk is not usable: {exc}",
            remediation="Repair or reinstall Python with Tcl/Tk support.",
        )

    return PreflightCheckResult(
        name="tkinter",
        passed=True,
        details="tkinter and Tcl/Tk are available.",
    )


def run_preflight() -> list[PreflightCheckResult]:
    return [
        _check_python_version(),
        _check_virtual_environment(),
        _check_tkinter(),
    ]


def all_checks_passed(results: Iterable[PreflightCheckResult]) -> bool:
    return all(item.passed for item in results)


def render_report(results: Iterable[PreflightCheckResult]) -> str:
    items = list(results)
    lines = ["TCP Simulator environment preflight", ""]

    for item in items:
        status = "PASS" if item.passed else "FAIL"
        lines.append(f"[{status}] {item.name}: {item.details}")
        if not item.passed and item.remediation:
            lines.append(f"       Fix: {item.remediation}")

    lines.append("")
    if all_checks_passed(items):
        lines.append("Preflight passed.")
    else:
        lines.append("Preflight failed.")

    return "\n".join(lines)
