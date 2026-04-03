from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    entrypoint = project_root / "scripts" / "run_tcp_sim.py"

    command = [
        sys.executable,
        "-m",
        "cx_Freeze",
        "--target-dir",
        str(project_root / "dist" / "cxfreeze"),
        str(entrypoint),
    ]
    return subprocess.call(command, cwd=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
