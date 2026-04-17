# TCP Server Simulator - Implementation Plan

> Status: Sender MVP complete; Receiver role in planning
> Last Updated: 2026-04-17
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

1. Functional requirements FR-01 through FR-71 marked MVP are implemented.
2. Non-functional requirements NFR-01 through NFR-13 are satisfied.
3. Automated suites pass for TM-INT-01, TM-INT-02, TM-INT-03, TM-INT-04, TM-SOAK-01, TM-SOAK-02, TM-SOAK-03.
4. GUI supports the **Sender ⇄ Receiver role toggle**, server/client modes, TCP/UDP, file preview (sender), sink-file panel (receiver), transport controls, status panel, and on-demand log load/refresh.
5. Runtime reconfiguration works without restart:
   - Rate updates take effect on next scheduler interval.
   - File swaps occur on safe boundary, preserve active connections, avoid old/new interleaving, and send new header once when enabled.
   - Sink-file enable/disable, format swap, and path change take effect at the next record boundary without connection drop.
6. Standalone `scripts/preflight.py` succeeds in a ready environment and fails with actionable remediation output in a broken environment.
7. App startup preflight reuses the same validator as `scripts/preflight.py` (no duplicated check logic).

### 2.1 Completion Status Snapshot (2026-04-17)

| Area | Status |
|------|--------|
| Phase 0 bootstrap (package, entrypoints, preflight, CI skeleton) | Complete |
| Phase 1 foundation (config + JSON logger + streaming file reader) | Complete |
| Phase 2 sender transport (TCP server/client + connection manager + backpressure) | Complete |
| Phase 3 UDP + scheduler + timestamp + runtime reconfiguration | Complete |
| Phase 4 sender GUI (controller + panels + log panel) | Complete |
| Transport module split (`_sender` variants, history-preserving rename) | Complete |
| **Phase 2b receiver transport + engine (framer, sink writer)** | **Not started** |
| **Phase 4b GUI role toggle + receiver/sink panels** | **Not started** |
| Phase 5 hardening / release candidate tag | Not started |

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

1. PR-01 Foundation skeleton + config + logging [merged]
2. PR-02 File reader and scan/index pipeline [merged]
3. PR-03 TCP server/client transport and backpressure [merged]
4. PR-04 UDP transport and recipient cache behavior [merged]
5. PR-05 Scheduler + timestamp rewrite + runtime file/rate reconfiguration [merged]
6. PR-06 GUI integration (controller + panels) [merged]
7. PR-07a Transport module split into `_sender` variants [merged]
8. **PR-07b `transport/base.py` extraction + sender class rename (`TcpServer`→`TcpServerSender`, etc.)**
9. **PR-08 `engine/framer.py` + `engine/sink_writer.py` with unit tests**
10. **PR-09 TCP receiver transports (`tcp_server_receiver.py`, `tcp_client_receiver.py`) + `engine/receiver.py`**
11. **PR-10 UDP receiver transports (`udp_server_receiver.py`, `udp_client_receiver.py`)**
12. **PR-11 GUI role toggle + receiver/sink panels + controller wiring for Receiver role**
13. **PR-12 Receiver integration + soak tests (TM-INT-04, TM-SOAK-03)**
14. PR-13 Soak hardening + docs + release readiness

Each PR should include:

1. Unit/integration tests for the new scope
2. Requirement ID references in PR description (for traceability)
3. Updated docs if behavior changed

---

## 5. Phase-by-Phase Execution

## Phase 0 - Bootstrap [COMPLETE]

Goal: Establish runnable package, test harness, and CI baseline.

Checklist:

- [x] Create source tree from Section 5.6 in design doc.
- [x] Add package entrypoints so `python -m tcp_sim` works.
- [x] Add `pyproject.toml` with editable install support.
- [x] Add venv-first bootstrap instructions for Windows and Linux.
- [x] Add runtime deps (stdlib-only target) and dev deps (`pytest`, `pytest-asyncio`, soak tooling as needed).
- [x] Add test markers for `unit`, `integration`, `soak`.
- [x] Add CI workflow skeleton with separate jobs for unit, integration, soak.
- [x] Add standalone `scripts/preflight.py` wired to shared preflight validator code.

Exit criteria:

1. Venv creation/activation plus `pip install -e .` succeeds on Windows and Linux.
2. `python scripts/preflight.py` returns zero in a ready environment.
3. `python scripts/preflight.py` returns non-zero with actionable diagnostics when prerequisites are intentionally broken.
4. `python -m tcp_sim --help` or equivalent launch path works.
5. Empty/smoke tests run in CI.

## Phase 1 - Foundation (Config, Logging, File Reader) [COMPLETE]

Goal: Implement stable core primitives before networking.

Scope:

1. Config schema, defaults, load/save, migration policy.
2. JSON structured logging with rotation and backup retention.
3. Streaming file reader with RFC 4180 parsing and progressive background scan.
4. Invalid-line tracking and discard behavior.
5. Shared preflight validator consumed by both startup and `scripts/preflight.py`.

Checklist:

- [x] Implement `config/config.py` with:
  - [x] `schema_version`
  - [x] deterministic migration for known old versions
  - [x] reject unknown/newer incompatible versions with warning and safe defaults
- [x] Implement shared preflight validator module used by app startup and `scripts/preflight.py`:
  - [x] Python version check (3.10+)
  - [x] active virtual environment check
  - [x] tkinter/Tk import/initialization check
  - [x] actionable remediation messages and non-zero failure codes
- [x] Implement `logging/json_logger.py` with:
  - [x] JSON records for connection and send events
  - [x] size-based rotation (`log_rotation_max_bytes`)
  - [x] retention count (`log_rotation_backup_count`, default 5)
- [x] Implement `engine/file_reader.py` with:
  - [x] streaming iteration (no full-file load)
  - [x] configurable delimiter
  - [x] header detection/send-header options
  - [x] RFC 4180 semantics (quoted fields, escaped quotes, embedded delimiters/newlines)
  - [x] progressive scan producing provisional counts
  - [x] per-record validation on emit path (protects send-before-scan-complete)
- [x] Unit tests for config migration, log formatting, parser correctness, invalid-line discards.

Exit criteria:

1. All Phase 1 unit tests pass.
2. Memory remains bounded while scanning multi-GB test file.
3. Invalid-line behavior matches FR-12/FR-12d in both scan and send paths.

## Phase 2 - Sender Transport (TCP + Backpressure + Reconnect) [COMPLETE]

Goal: Deliver robust TCP behavior under churn and slow clients.

Scope:

1. TCP server broadcast and connection lifecycle handling.
2. TCP client auto-reconnect with exponential backoff.
3. Connection manager with per-client queues, watermarks, and hard cap disconnect.
4. Timeout support and lifecycle event logging.

Checklist:

- [x] Implement `transport/tcp_server_sender.py` (originally `tcp_server.py`):
  - [x] broadcast to all connected clients
  - [x] late-join clients receive current stream position
  - [x] expected connect/disconnect churn logged as INFO
  - [x] zero-subscriber pause hooks for scheduler
- [x] Implement `transport/tcp_client_sender.py` (originally `tcp_client.py`):
  - [x] reconnect backoff (1s, 2s, 4s, ... max configurable)
  - [x] reconnect counters/status events
- [x] Implement `transport/connection_manager.py`:
  - [x] per-client outbound queues
  - [x] high/low watermark state transitions
  - [x] timeout-based slow-client disconnect
  - [x] hard cap immediate disconnect
- [x] Integration tests for TM-INT-01, TM-INT-02, TM-INT-03 baseline behavior.

Exit criteria:

1. TM-INT-01/02/03 pass at baseline profile.
2. Slow clients do not stall healthy clients.
3. No leaked sessions after reconnect storms.

## Phase 2b - Transport Base + Receiver Role

Goal: Add Receiver role across all four transport+mode combinations with an optional sink file, extracting the now-shared socket primitives into `transport/base.py`.

Scope:

1. Extract shared transport primitives into `transport/base.py` (socket bind/connect helpers, shutdown protocol, event emitter shape, shared backoff/reconnect helper).
2. Rename sender-side exported classes for symmetry: `TcpServer` → `TcpServerSender`, `TcpClient` → `TcpClientSender`, `UdpServer` → `UdpServerSender`, `UdpClient` → `UdpClientSender`. Update controller and test imports.
3. Implement `engine/framer.py` (record-separator TCP framer; pure-function core; unit-testable without sockets).
4. Implement `engine/sink_writer.py` (delimited passthrough + JSONL; size rotation; bounded queue with high/low watermarks; runtime enable/disable/format/path swap).
5. Implement the four receiver transports on top of `base.py`.
6. Implement `engine/receiver.py` orchestrator exposing the same event/callback surface the controller uses for the sender.
7. Receiver-side backpressure: per-peer TCP read pause above sink high watermark; UDP drop-and-count above cap.

Checklist:

- [ ] Create `transport/base.py` and migrate shared primitives out of existing `_sender` modules.
- [ ] Rename sender classes (`TcpServer`→`TcpServerSender`, etc.) and update all imports in `gui/controller.py` and `tests/`.
- [ ] Implement `engine/framer.py`:
  - [ ] stream buffer + record-separator split (`\n`, `\r\n`, raw-chunk)
  - [ ] configurable `receiver_max_record_bytes` with truncation flag
  - [ ] incremental-feed API (accept byte chunks, yield complete records)
- [ ] Implement `engine/sink_writer.py`:
  - [ ] delimited passthrough format
  - [ ] JSONL format (`ts`, `src`, `bytes_len`, `payload`, `truncated`, `encoding` when base64)
  - [ ] size-based rotation with configurable `sink_rotation_max_bytes` + `sink_rotation_backup_count`
  - [ ] bounded queue with `sink_queue_high_watermark_bytes` / `sink_queue_low_watermark_bytes`
  - [ ] runtime enable/disable, format swap, and path swap at next record boundary
- [ ] Implement `transport/tcp_server_receiver.py`:
  - [ ] accept loop + per-peer read task
  - [ ] per-peer framing via `engine/framer.py`
  - [ ] per-peer read pause when sink queue exceeds high watermark; resume below low watermark
  - [ ] lifecycle churn logged as INFO (FR-04a parity)
- [ ] Implement `transport/tcp_client_receiver.py`:
  - [ ] outbound connect + read loop + framing
  - [ ] reuse shared auto-reconnect backoff from `transport/base.py`
  - [ ] reconnect counter events
- [ ] Implement `transport/udp_server_receiver.py`:
  - [ ] bind + datagram receive loop (one datagram = one record)
  - [ ] optional multicast group join
  - [ ] UDP drop-and-count when sink queue exceeds cap
  - [ ] record source address for JSONL `src` field
- [ ] Implement `transport/udp_client_receiver.py`:
  - [ ] bind ephemeral + receive loop
  - [ ] optional "hello" datagram to remote host:port at startup
- [ ] Implement `engine/receiver.py`:
  - [ ] orchestrate transport + framer + sink writer
  - [ ] emit receive stats events (records, bytes, peers, sink state, drops, truncations)
  - [ ] clean shutdown with sink flush and close
- [ ] Unit tests:
  - [ ] `test_framer.py` (separator variants, truncation, partial chunks, CRLF across chunks)
  - [ ] `test_sink_writer.py` (both formats, rotation, backup retention, base64 fallback, runtime path/format swap, queue watermark transitions)
- [ ] Integration tests:
  - [ ] `test_receiver_tcp_server.py` + `test_receiver_tcp_client.py` + `test_receiver_udp.py` + `test_receiver_sink_formats_and_rotation.py` (together satisfy TM-INT-04)

Exit criteria:

1. Unit tests for framer and sink writer pass.
2. TM-INT-04 integration tests pass for all four role+mode combinations and both sink formats.
3. Sink enable/disable/format/path swap during active receive produces no dropped records on TCP peers.
4. TCP per-peer read pause activates above high watermark and clears below low watermark.
5. UDP drop counter is monotonic and bounded under sink overload.

## Phase 3 - UDP + Scheduler + Timestamp + Runtime Reconfiguration [COMPLETE]

Goal: Complete engine-level send semantics and timing controls.

Scope:

1. UDP client and UDP server modes.
2. Reply-to-senders recipient cache (TTL/cap/cleanup/eviction).
3. Scheduler modes: auto, pause/resume, step, jump-to-line, loop.
4. Timestamp rewrite behavior and UTC/monotonic policy.
5. Runtime rate change and file swap without restart.

Checklist:

- [x] Implement `transport/udp_server_sender.py` (originally `udp_server.py`):
  - [x] multicast mode
  - [x] reply-to-senders mode
  - [x] recipient cache maintenance (TTL, cap, cleanup interval, LRU default)
- [x] Implement `transport/udp_client_sender.py` (originally `udp_client.py`) send path.
- [x] Implement `engine/scheduler.py`:
  - [x] features/s scheduling
  - [x] zero-client pause semantics in server broadcast mode
  - [x] step mode and jump-to-line semantics (1-based, header and discarded rows excluded)
  - [x] loop behavior at EOF
  - [x] runtime rate update on next interval
- [x] Implement file swap generation safety:
  - [x] switch at message boundary
  - [x] no old/new interleaving per client
  - [x] optional new-header emit for connected clients when enabled
- [x] Implement `engine/timestamp.py`:
  - [x] ISO 8601, epoch millis, epoch seconds integer/fractional
  - [x] UTC normalization for parsed timestamps
  - [x] monotonic clock for schedule delay
- [x] Add and run soak scenarios TM-SOAK-01 and TM-SOAK-02 baseline.

Exit criteria:

1. Scheduler modes function without connection drops.
2. Runtime file/rate reconfiguration works exactly per FR-20c to FR-20f.
3. TM-SOAK-01 and TM-SOAK-02 baseline pass.

## Phase 4 - Sender GUI Integration [COMPLETE]

Goal: Deliver full MVP user workflow with responsive tkinter UI.

Scope:

1. Controller bridge between tkinter thread and asyncio engine loop.
2. All required panels and controls.
3. Real-time status metrics and on-demand log panel.
4. Startup preflight and user-facing error guidance.

Checklist:

- [x] Implement `gui/app.py` and controller wiring.
- [x] Implement `gui/config_panel.py`:
  - [x] mode/protocol switching with controlled stop/rebind transition
  - [x] host/port/timeouts/backoff
- [x] Implement `gui/file_panel.py`:
  - [x] browse/load file
  - [x] first 10 rows preview
  - [x] invalid rows highlighted and discarded count
- [x] Implement `gui/control_panel.py`:
  - [x] start/pause/stop/step/jump
  - [x] loop toggle
  - [x] rate controls and live rate changes
  - [x] runtime file swap control
- [x] Implement `gui/status_panel.py`:
  - [x] connected clients
  - [x] blocked/disconnected slow clients
  - [x] line/progress/features-s/KB-s/elapsed
- [x] Implement `gui/log_panel.py`:
  - [x] on-demand load
  - [x] on-demand refresh
  - [x] no automatic live tail
- [x] Implement startup preflight checks and actionable dialogs/messages.

Exit criteria:

1. End-to-end manual flow works in both server and client modes.
2. GUI remains responsive during active transmission and scans.
3. Config save/load and auto-load-last-config behavior works.

## Phase 4b - GUI Role Toggle + Receiver/Sink Panels

Goal: Wire the Sender ⇄ Receiver role toggle end-to-end through the controller, and add receiver-only GUI surfaces.

Scope:

1. Role toggle (Sender / Receiver) at the top of the window. Default Sender.
2. Controller-layer routing: in Sender role, drive `engine/simulator.py`; in Receiver role, drive `engine/receiver.py`. Role switching performs controlled stop/rebind (FR-03a extended to role).
3. Contextual show/hide or enable/disable of panels per active role (FR-04c).
4. Receiver-only sink panel: enable toggle, format selector (delimited / JSONL), path browser, max record bytes, rotation settings, sink status (current size, rotations).
5. Receiver status metrics in `status_panel.py`: records/s, KB/s, total records, total bytes, peer count (server) or connection state (client), UDP drops, truncation count.
6. Config save/load: extend persistence to cover `role` and the `receiver` config object.

Checklist:

- [ ] Add role toggle widget to `gui/app.py`.
- [ ] Extend `gui/controller.py` with role-aware start/stop dispatch between `Simulator` and `Receiver`.
- [ ] Add `gui/sink_panel.py` (or extend `file_panel.py`) for receiver-only sink controls.
- [ ] Update `gui/config_panel.py` so role-invalid controls are disabled or hidden.
- [ ] Update `gui/control_panel.py` so sender-only controls (rate, step, loop, jump, file swap) are hidden in Receiver role.
- [ ] Update `gui/status_panel.py` to surface receiver metrics when in Receiver role.
- [ ] Update `config/config.py` schema: add `role` (`sender`|`receiver`) and `receiver` object. Bump `schema_version`. Add migration from previous version (absent fields → defaults: role=`sender`, sink disabled).
- [ ] Unit tests for config migration adding receiver section.
- [ ] Manual smoke test matrix: all four role+mode+protocol combinations launch, stop, and restart cleanly.

Exit criteria:

1. Role toggle switches pipeline cleanly with no residual tasks or leaked sockets.
2. Contextual controls are disabled/hidden per active role.
3. Sink panel enable/disable/format/path changes round-trip through config save/load.
4. All sender-side MVP flows continue to work unchanged in Sender role.

## Phase 5 - Hardening and MVP Signoff

Goal: Enforce quality gates and lock release candidate.

Checklist:

- [ ] Run full unit + integration + soak gates in CI (including TM-INT-04 and TM-SOAK-03).
- [ ] Verify threshold checks are enforced (build fails on any matrix violation).
- [ ] Add troubleshooting and runbook sections to README, including Receiver role usage and sink file operation.
- [ ] Validate fresh setup on Windows and Linux.
- [ ] Perform exploratory socket-tool checks (non-gating), including receive-side validation against a known publisher.
- [ ] Tag MVP release candidate only after all gates are green.

Exit criteria:

1. All automated MVP matrix scenarios pass in CI (TM-INT-01 through TM-INT-04; TM-SOAK-01 through TM-SOAK-03).
2. No open Severity-1/Severity-2 defects.
3. Documentation updated for setup, usage, receiver role, sink file behavior, and known limitations.

---

## 6. Test Implementation Plan

Implement tests in parallel with each module, not at the end.

Recommended minimum structure:

1. `tests/unit`
   - `test_file_reader.py` [done]
   - `test_scheduler.py` [done]
   - `test_timestamp.py` [done]
   - `test_config.py` [done]
   - `test_json_logger.py` [done]
   - `test_log_panel.py` [done]
   - `test_tls_transport.py` [done]
   - **`test_framer.py`** [Phase 2b]
   - **`test_sink_writer.py`** [Phase 2b]
2. `tests/integration`
   - `test_tcp_server_reconnect_storm.py` (TM-INT-01) [done]
   - `test_tcp_client_reconnect_storm.py` (TM-INT-02) [done]
   - `test_slow_client_churn_backpressure.py` (TM-INT-03) [done]
   - `test_tcp_server_header_order.py` [done]
   - `test_udp_reply_to_senders_cache.py` (supports TM-SOAK-02 setup) [done]
   - `test_controller_streaming.py` [done]
   - **`test_receiver_tcp_server.py`** (TM-INT-04) [Phase 2b]
   - **`test_receiver_tcp_client.py`** (TM-INT-04) [Phase 2b]
   - **`test_receiver_udp.py`** (TM-INT-04) [Phase 2b]
   - **`test_receiver_sink_formats_and_rotation.py`** (TM-INT-04) [Phase 2b]
3. `tests/soak`
   - `test_large_file_streaming_stability.py` (TM-SOAK-01) [done]
   - `test_udp_recipient_cache_stability.py` (TM-SOAK-02) [done]
   - **`test_receiver_sink_rotation_backpressure.py`** (TM-SOAK-03) [Phase 2b/5]

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

Sender-side Phases 0–4 are complete. Receiver work is the critical path. Start with these in order:

1. **PR-07b:** Extract `transport/base.py` from the existing `_sender` modules and rename exported classes (`TcpServer`→`TcpServerSender`, etc.). Keep behavior identical; tests must still pass.
2. **PR-08:** Implement `engine/framer.py` and `engine/sink_writer.py` with full unit test coverage. No sockets required.
3. **PR-09:** Implement `tcp_server_receiver.py` + `tcp_client_receiver.py` + `engine/receiver.py` on top of `base.py`. Add TCP receiver integration tests.
4. **PR-10:** Implement `udp_server_receiver.py` + `udp_client_receiver.py`. Add UDP receiver integration tests, completing TM-INT-04.
5. **PR-11:** Extend `config/config.py` schema (bump `schema_version`, migration for `role` + `receiver`). Wire the Sender ⇄ Receiver role toggle through `gui/controller.py` and add the receiver/sink GUI panels.
6. **PR-12:** Add TM-SOAK-03 soak test.
7. **PR-13:** Phase 5 hardening, docs, release candidate tag.

File the `transport/base.py` extraction first. Every downstream task benefits from it and the diff is self-contained.
