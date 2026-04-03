from tcp_sim.preflight import all_checks_passed, render_report, run_preflight


def main() -> int:
    results = run_preflight()
    print(render_report(results))
    return 0 if all_checks_passed(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
