# TCP Server Simulator - Implementation Plan

> Status: Ready to Execute
> Last Updated: 2026-04-02
> Canonical Requirements: docs/design-and-requirements.md

---

## 1. Purpose

This plan translates the approved requirements into an implementation sequence you can follow without guessing. It is optimized for:

1. Early risk reduction (async transport, backpressure, large files)
2. Fast feedback through automated tests
3. Clear MVP completion gates

---

## 2. MVP Definition of Done

MVP is complete only when all of the following are true:

1. Functional requirements FR-01 through FR-55 marked MVP are implemented.
2. Non-functional requirements NFR-01 through NFR-13 are satisfied.
3. Automated suites pass for TM-INT-01, TM-INT-02, TM-INT-03, TM-SOAK-01, TM-SOAK-02.
4. GUI supports server/client modes, TCP/UDP, file preview, transport controls, status panel, and on-demand log load/refresh.
5. Runtime reconfiguration works without restart:
   - Rate updates take effect on next scheduler interval.
   - File swaps occur on safe boundary, preserve active connections, avoid old/new interleaving, and send new header once when enabled.
6. Standalone `scripts/preflight.py` succeeds in a ready environment and fails with actionable remediation output in a broken environment.
7. App startup preflight reuses the same validator as `scripts/preflight.py` (no duplicated check logic).

---

## 3. Implementation Principles

1. Keep business logic out of GUI modules.
2. Build engine first, GUI second.
3. Every feature lands with tests in the same PR.
4. Prefer deterministic behavior over convenience in transport and scheduling.
5. Preserve wire-level correctness over UI speed if tradeoffs appear.

---

## 4. Suggested Branch and PR Strategy

Use small, mergeable PRs in this order:

1. PR-01 Foundation skeleton + config + logging
2. PR-02 File reader and scan/index pipeline
3. PR-03 TCP server/client transport and backpressure
4. PR-04 UDP transport and recipient cache behavior
5. PR-05 Scheduler + timestamp rewrite + runtime file/rate reconfiguration
6. PR-06 GUI integration (controller + panels)
7. PR-07 Soak hardening + docs + release readiness

Each PR should include:

1. Unit/integration tests for the new scope
2. Requirement ID references in PR description (for traceability)
3. Updated docs if behavior changed

---

## 5. Phase-by-Phase Execution

## Phase 0 - Bootstrap

Goal: Establish runnable package, test harness, and CI baseline.

Checklist:

- [ ] Create source tree from Section 5.6 in design doc.
- [ ] Add package entrypoints so `python -m tcp_sim` works.
- [ ] Add `pyproject.toml` with editable install support.
- [ ] Add venv-first bootstrap instructions for Windows and Linux.
- [ ] Add runtime deps (stdlib-only target) and dev deps (`pytest`, `pytest-asyncio`, soak tooling as needed).
- [ ] Add test markers for `unit`, `integration`, `soak`.
- [ ] Add CI workflow skeleton with separate jobs for unit, integration, soak.
- [ ] Add standalone `scripts/preflight.py` wired to shared preflight validator code.

Exit criteria:

1. Venv creation/activation plus `pip install -e .` succeeds on Windows and Linux.
2. `python scripts/preflight.py` returns zero in a ready environment.
3. `python scripts/preflight.py` returns non-zero with actionable diagnostics when prerequisites are intentionally broken.
4. `python -m tcp_sim --help` or equivalent launch path works.
5. Empty/smoke tests run in CI.

## Phase 1 - Foundation (Config, Logging, File Reader)

Goal: Implement stable core primitives before networking.

Scope:

1. Config schema, defaults, load/save, migration policy.
2. JSON structured logging with rotation and backup retention.
3. Streaming file reader with RFC 4180 parsing and progressive background scan.
4. Invalid-line tracking and discard behavior.
5. Shared preflight validator consumed by both startup and `scripts/preflight.py`.

Checklist:

- [ ] Implement `config/config.py` with:
  - [ ] `schema_version`
  - [ ] deterministic migration for known old versions
  - [ ] reject unknown/newer incompatible versions with warning and safe defaults
- [ ] Implement shared preflight validator module used by app startup and `scripts/preflight.py`:
  - [ ] Python version check (3.10+)
  - [ ] active virtual environment check
  - [ ] tkinter/Tk import/initialization check
  - [ ] actionable remediation messages and non-zero failure codes
- [ ] Implement `logging/json_logger.py` with:
  - [ ] JSON records for connection and send events
  - [ ] size-based rotation (`log_rotation_max_bytes`)
  - [ ] retention count (`log_rotation_backup_count`, default 5)
- [ ] Implement `engine/file_reader.py` with:
  - [ ] streaming iteration (no full-file load)
  - [ ] configurable delimiter
  - [ ] header detection/send-header options
  - [ ] RFC 4180 semantics (quoted fields, escaped quotes, embedded delimiters/newlines)
  - [ ] progressive scan producing provisional counts
  - [ ] per-record validation on emit path (protects send-before-scan-complete)
- [ ] Unit tests for config migration, log formatting, parser correctness, invalid-line discards.

Exit criteria:

1. All Phase 1 unit tests pass.
2. Memory remains bounded while scanning multi-GB test file.
3. Invalid-line behavior matches FR-12/FR-12d in both scan and send paths.

## Phase 2 - Transport (TCP + Backpressure + Reconnect)

Goal: Deliver robust TCP behavior under churn and slow clients.

Scope:

1. TCP server broadcast and connection lifecycle handling.
2. TCP client auto-reconnect with exponential backoff.
3. Connection manager with per-client queues, watermarks, and hard cap disconnect.
4. Timeout support and lifecycle event logging.

Checklist:

- [ ] Implement `transport/tcp_server.py`:
  - [ ] broadcast to all connected clients
  - [ ] late-join clients receive current stream position
  - [ ] expected connect/disconnect churn logged as INFO
  - [ ] zero-subscriber pause hooks for scheduler
- [ ] Implement `transport/tcp_client.py`:
  - [ ] reconnect backoff (1s, 2s, 4s, ... max configurable)
  - [ ] reconnect counters/status events
- [ ] Implement `transport/connection_manager.py`:
  - [ ] per-client outbound queues
  - [ ] high/low watermark state transitions
  - [ ] timeout-based slow-client disconnect
  - [ ] hard cap immediate disconnect
- [ ] Integration tests for TM-INT-01, TM-INT-02, TM-INT-03 baseline behavior.

Exit criteria:

1. TM-INT-01/02/03 pass at baseline profile.
2. Slow clients do not stall healthy clients.
3. No leaked sessions after reconnect storms.

## Phase 3 - UDP + Scheduler + Timestamp + Runtime Reconfiguration

Goal: Complete engine-level send semantics and timing controls.

Scope:

1. UDP client and UDP server modes.
2. Reply-to-senders recipient cache (TTL/cap/cleanup/eviction).
3. Scheduler modes: auto, pause/resume, step, jump-to-line, loop.
4. Timestamp rewrite behavior and UTC/monotonic policy.
5. Runtime rate change and file swap without restart.

Checklist:

- [ ] Implement `transport/udp_server.py`:
  - [ ] multicast mode
  - [ ] reply-to-senders mode
  - [ ] recipient cache maintenance (TTL, cap, cleanup interval, LRU default)
- [ ] Implement `transport/udp_client.py` send path.
- [ ] Implement `engine/scheduler.py`:
  - [ ] features/s scheduling
  - [ ] zero-client pause semantics in server broadcast mode
  - [ ] step mode and jump-to-line semantics (1-based, header and discarded rows excluded)
  - [ ] loop behavior at EOF
  - [ ] runtime rate update on next interval
- [ ] Implement file swap generation safety:
  - [ ] switch at message boundary
  - [ ] no old/new interleaving per client
  - [ ] optional new-header emit for connected clients when enabled
- [ ] Implement `engine/timestamp.py`:
  - [ ] ISO 8601, epoch millis, epoch seconds integer/fractional
  - [ ] UTC normalization for parsed timestamps
  - [ ] monotonic clock for schedule delay
- [ ] Add and run soak scenarios TM-SOAK-01 and TM-SOAK-02 baseline.

Exit criteria:

1. Scheduler modes function without connection drops.
2. Runtime file/rate reconfiguration works exactly per FR-20c to FR-20f.
3. TM-SOAK-01 and TM-SOAK-02 baseline pass.

## Phase 4 - GUI Integration

Goal: Deliver full MVP user workflow with responsive tkinter UI.

Scope:

1. Controller bridge between tkinter thread and asyncio engine loop.
2. All required panels and controls.
3. Real-time status metrics and on-demand log panel.
4. Startup preflight and user-facing error guidance.

Checklist:

- [ ] Implement `gui/app.py` and controller wiring.
- [ ] Implement `gui/config_panel.py`:
  - [ ] mode/protocol switching with controlled stop/rebind transition
  - [ ] host/port/timeouts/backoff
- [ ] Implement `gui/file_panel.py`:
  - [ ] browse/load file
  - [ ] first 10 rows preview
  - [ ] invalid rows highlighted and discarded count
- [ ] Implement `gui/control_panel.py`:
  - [ ] start/pause/stop/step/jump
  - [ ] loop toggle
  - [ ] rate controls and live rate changes
  - [ ] runtime file swap control
- [ ] Implement `gui/status_panel.py`:
  - [ ] connected clients
  - [ ] blocked/disconnected slow clients
  - [ ] line/progress/features-s/KB-s/elapsed
- [ ] Implement `gui/log_panel.py`:
  - [ ] on-demand load
  - [ ] on-demand refresh
  - [ ] no automatic live tail
- [ ] Implement startup preflight checks and actionable dialogs/messages.

Exit criteria:

1. End-to-end manual flow works in both server and client modes.
2. GUI remains responsive during active transmission and scans.
3. Config save/load and auto-load-last-config behavior works.

## Phase 5 - Hardening and MVP Signoff

Goal: Enforce quality gates and lock release candidate.

Checklist:

- [ ] Run full unit + integration + soak gates in CI.
- [ ] Verify threshold checks are enforced (build fails on any matrix violation).
- [ ] Add troubleshooting and runbook sections to README.
- [ ] Validate fresh setup on Windows and Linux.
- [ ] Perform exploratory socket-tool checks (non-gating).
- [ ] Tag MVP release candidate only after all gates are green.

Exit criteria:

1. All automated MVP matrix scenarios pass in CI.
2. No open Severity-1/Severity-2 defects.
3. Documentation updated for setup, usage, and known limitations.

---

## 6. Test Implementation Plan

Implement tests in parallel with each module, not at the end.

Recommended minimum structure:

1. `tests/unit`
   - `test_file_reader.py`
   - `test_scheduler.py`
   - `test_timestamp.py`
   - `test_config.py`
2. `tests/integration`
   - `test_tcp_server_reconnect_storm.py` (TM-INT-01)
   - `test_tcp_client_reconnect_storm.py` (TM-INT-02)
   - `test_slow_client_churn_backpressure.py` (TM-INT-03)
   - `test_udp_reply_to_senders_cache.py` (supports TM-SOAK-02 setup)
3. `tests/soak`
   - `test_large_file_streaming_stability.py` (TM-SOAK-01)

Suggested commands:

```bash
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
python scripts/preflight.py

# Linux
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
python scripts/preflight.py

# Tests (with venv active)
pytest -m unit -q
pytest -m integration -q
pytest -m soak -q
```

---

## 7. Requirement Traceability Workflow

For every PR, include a simple mapping table in the PR description:

1. Requirement IDs implemented (for example: FR-31, FR-32a, FR-32b)
2. Test IDs added/updated (for example: TM-INT-03)
3. Risk(s) mitigated (from Risk Register Section 7)

This keeps implementation aligned with the spec and prevents drift.

---

## 8. Immediate Next Actions

Start with these in order:

1. Scaffold package and CI baseline (Phase 0).
2. Implement config + logger + file reader with unit tests (Phase 1).
3. Open first integration PR for TCP transport + reconnect + backpressure (Phase 2).

If execution needs to accelerate, run Phase 4 GUI wiring in parallel with late Phase 3, but do not bypass test gates.
