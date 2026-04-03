from __future__ import annotations

import argparse

from .gui.app import App
from .preflight import all_checks_passed, render_report, run_preflight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tcp_sim",
        description="TCP Server Simulator bootstrap entrypoint.",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="Run environment checks and exit.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Do not launch tkinter GUI after preflight.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    results = run_preflight()
    report = render_report(results)

    if args.preflight_only:
        print(report)
        return 0 if all_checks_passed(results) else 1

    if not all_checks_passed(results):
        print(report)
        print("\nEnvironment is not ready. Resolve failures and try again.")
        return 1

    if args.headless:
        print("Preflight passed. Headless mode requested.")
        return 0

    app = App()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
