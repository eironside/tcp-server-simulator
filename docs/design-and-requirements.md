# TCP Server Simulator — Design & Requirements Document

> **Status:** READY FOR IMPLEMENTATION — All design decisions resolved  
> **Last Updated:** 2026-04-17  
> **Target Platforms:** Windows, Linux  
> **Language:** Python 3.10+  
> **GUI Framework:** tkinter (stdlib)  
> **Distribution:** Source only (for now)  
> **Interface:** GUI (with underlying engine decoupled for future CLI use)

---

## 1. Overview

A cross-platform TCP/UDP traffic simulator for testing ArcGIS Velocity. The tool can either **transmit** delimited text files (primarily CSV) line-by-line at a configurable rate, or **receive** TCP/UDP traffic and optionally persist it to disk. Two orthogonal user-selectable axes define runtime behavior:

- **Role / Direction** — **Sender** (emit data from a loaded file) or **Receiver** (accept and capture inbound data).
- **Transport mode** — **Server** (bind and listen) or **Client** (connect outbound). Valid in both Sender and Receiver roles.

This produces four supported operating combinations:

| Role | Mode | Behavior |
|------|------|----------|
| Sender | Server | Listen, accept inbound connections, broadcast file data to connected clients. |
| Sender | Client | Connect outbound to a remote host:port and push file data. |
| Receiver | Server | Listen on a port, accept inbound connections, consume inbound data (optionally write to a sink file). |
| Receiver | Client | Connect outbound to a remote server and consume inbound data from it (optionally write to a sink file). |

The role is switched via a **Sender ⇄ Receiver toggle** in the GUI and applies independently of the Server/Client mode toggle and the TCP/UDP protocol toggle.

The tool is a spiritual successor to the GeoEvent TCP Simulator (Java), rebuilt for modern use. This is a clean-slate design with no backward compatibility requirements.

**Primary Users:** Product Engineers testing ArcGIS Velocity for Enterprise product functionality. The tool is interactive-first, not designed for CI pipeline automation.

> **Reference Material:** The `docs/previous/` directory contains Confluence exports documenting how PEs previously tested Velocity TCP feeds using crude Python scripts and SocketTest. These informed the testing context below but do not define requirements for this tool.

### 1.1 Velocity Testing Context

Understanding how ArcGIS Velocity uses TCP connections is essential because it dictates server mode behavior.

**Velocity TCP Client Feed (our primary use case):**
Velocity acts as a TCP client that connects to an external TCP server to ingest data. Our simulator in **Server mode** fills the role of that external TCP server.

```
┌───────────────────┐         ┌───────────────────┐
│  Our Simulator     │◄────────│  ArcGIS Velocity   │
│  (Server mode)     │────────►│  (TCP Client Feed)  │
│  Sends CSV lines   │         │  Ingests data       │
└───────────────────┘         └───────────────────┘
```

**Velocity's connection lifecycle during feed setup:**
1. **testConnection** — Velocity connects to verify the server is reachable, then disconnects.
2. **sampleMessages** — Velocity reconnects and reads a few messages to derive the data schema, then disconnects.
3. **Feed run** — Velocity reconnects a final time for the actual data feed.

This connect → disconnect → reconnect pattern happens every time a feed is configured. Previous tools (SocketTest, simple Python scripts) broke here because they couldn't handle the repeated disconnections. **Our server mode must treat this as normal behavior** — connections that come and go are expected, not errors.

**Velocity TCP Client Output (now in scope):**
Velocity RATs can output data to an external TCP server. In this scenario our simulator runs in **Receiver role, Server mode** and captures that output, optionally streaming it to a delimited or JSON sink file for offline inspection. This is the primary motivation for adding receiver support.

**Velocity TCP Server Feed (reverse direction):**
Our simulator in **Sender role, Client mode** connects to Velocity's TCP Server feed to push data inward. Less commonly tested but supported. The mirror case — **Receiver role, Client mode** — can pull data from an external TCP server that pushes to connected clients (e.g., a Velocity RAT configured as a TCP client output that the tester points our receiver at via an intermediary, or third-party publishers).

### 1.2 Data Format Considerations

The simulator sends line-oriented text records terminated by a configurable record separator. The downstream consumer (Velocity) interprets payload semantics.

Velocity supports these formats for TCP feeds:
- Delimited (comma, pipe, semicolon, tab — our primary focus)
- JSON
- GeoJSON
- EsriJSON
- XML

For this simulator MVP, requirements are defined for **delimited text inputs** (CSV/TSV/custom delimiter). Support for non-delimited payloads is not a guaranteed MVP behavior.

---

## 2. Resolved Design Decisions

These answers were provided by the project owner and inform all requirements below.

| # | Decision | Answer | MVP? |
|---|----------|--------|------|
| Q1 | Language/Runtime | **Python 3.10+** with `asyncio` | Yes |
| Q2 | Distribution | **Source only** (defer packaging decisions) | Yes |
| Q3 | Interface | **GUI required** | Yes |
| Q4 | Server broadcast model | **Broadcast** — all clients see same stream, late joiners get current line | Yes |
| Q5 | Header row | **Configurable** — user can opt to exclude header from transmission | Yes |
| Q6 | TLS/SSL | **Post-MVP** — plan for it architecturally, don't implement yet | No |
| Q7 | Client auto-reconnect | **Yes** with reconnect indicator/count in UI and logs | Yes |
| Q8 | Backpressure | **Block and disconnect slow clients** with UI indicator showing blocking status and which clients were disconnected | Yes |
| Q9 | UDP support | **Yes** — support both TCP and UDP | Yes |
| Q10 | Rate unit | **Features/second** (1 line = 1 feature). Also report KB/s. Post-MVP: original-timestamp replay rate mode | Yes (features/s), Post-MVP (original-rate) |
| Q11 | Original-timestamp replay | **Yes, post-MVP** — still allow timestamp replacement with current time | No |
| Q12 | Timestamp formats | **ISO 8601, epoch millis, epoch seconds** (integer and fractional). Auto-detect post-MVP | Yes (explicit), No (auto-detect) |
| Q13 | CSV validation | **Yes** — discard lines with inconsistent column count | Yes |
| Q14 | Max file size | **No limit** — stream the file, don't load into memory | Yes |
| Q15 | Line navigation and subsetting | **MVP:** jump-to-line in step mode. **Post-MVP:** start/end line and first N lines. No random sampling. | Yes (jump), No (range/N) |
| Q16 | Log format | **JSON structured**. Post-MVP: log viewer UI component | Yes (JSON), No (viewer) |
| Q17 | Config files | **Yes, JSON format** | Yes |
| Q18 | GeoEvent compatibility | **No** — clean-slate design | N/A |
| Q19 | Primary users | **Product Engineers** testing ArcGIS Velocity for Enterprise | N/A |
| Q20 | Multiple files | **No** — single file per instance. Run separate copies for separate files. | Yes |
| RQ1 | GUI framework | **tkinter** (stdlib). It doesn't have to be nice. | Yes |
| RQ2 | Dark mode / theming | **No** | N/A |
| RQ3 | UDP server recipient discovery | **Both** — support multicast and reply-to-senders, user-selectable | Yes |
| RQ4 | Slow-client disconnect timeout | **Configurable**, default **10 seconds** | Yes |
| RQ5 | Max reconnect backoff (client) | **Configurable**, default **30 seconds** | Yes |
| RQ6 | Preview rows in GUI | **10 rows** | Yes |
| RQ7 | Show discarded lines in preview | **Yes** — highlighted red, with total discarded count | Yes |
| RQ8 | Remember last config on startup | **Yes** — auto-load last-used config | Yes |
| RQ9 | Log rotation | **Configurable** with sensible default (10 MB) | Yes |
| RQ10 | Server broadcast with zero subscribers | **Pause transmission** until at least one client is connected | Yes |
| RQ11 | Connect/send timeout defaults | **10 seconds** each (configurable) | Yes |
| RQ12 | UDP recipient cache defaults | TTL **300 seconds**, cap **256 recipients**, cleanup interval **30 seconds**, LRU eviction (configurable) | Yes |
| RQ13 | Config schema migration policy | **Hybrid**: migrate known older versions; invalidate unknown/incompatible versions and load defaults with warning | Yes |
| RQ14 | Large file indexing/validation strategy | Background progressive scan; transmission can start before scan completes; counts remain provisional until finalized | Yes |
| RQ15 | Backpressure queue model | Per-client outbound queue with high/low watermarks and hard cap | Yes |
| RQ16 | CSV parsing semantics | RFC 4180-style quoted-field handling including embedded delimiters/newlines | Yes |
| RQ17 | Timestamp clock/timezone policy | Normalize parsed timestamps to UTC; use monotonic clock for scheduling delays | Yes |
| RQ18 | Standalone runtime preflight | Provide standalone `scripts/preflight.py` and run the same checks at startup. Validate Python version, active virtual environment, and tkinter/Tk availability with actionable errors. | Yes |
| RQ19 | GUI log monitoring mode | **No live monitoring**; load and refresh logs on demand | Yes |
| RQ20 | Test strategy depth | **Mandatory automated integration + soak suites** for reconnect storms, slow-client churn, and large-file streaming/resource stability | Yes |
| RQ21 | Runtime reconfiguration behavior | Change rate and data file without restarting app; apply rate immediately and swap file at next safe boundary | Yes |
| RQ22 | Sender/Receiver role | **Toggle in GUI** between Sender and Receiver roles. Orthogonal to Server/Client mode and TCP/UDP protocol. Switching roles performs a controlled stop/rebind like FR-03a. | Yes |
| RQ23 | Receiver sink output | **Optional** sink-to-file. Disabled by default (metrics-only). When enabled, each received message is appended to a configurable sink file. | Yes |
| RQ24 | Sink file formats | **Delimited passthrough** (write received bytes verbatim, split on configured record separator) and **JSON Lines** (one JSON object per line: `{ts, src, bytes_len, payload}` with payload as UTF-8 string, or base64 if non-UTF-8). | Yes |
| RQ25 | Sink file rotation/size | Same rotation policy model as log files: configurable max bytes (default 100 MB) and configurable backup count (default 5). | Yes |
| RQ26 | Receiver framing | TCP: split on configured record separator (default `\n`), same terminator options as sender (`\n`, `\r\n`, none=length-prefixed not required, raw-chunk). UDP: each datagram is one record. Oversized records (> configurable max record bytes, default 1 MiB) are truncated and logged. | Yes |

---

## 3. Functional Requirements

### 3.1 Operating Modes

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The application shall support **Server mode**: bind to a port and accept TCP connections (sender broadcasts, receiver consumes). | MVP |
| FR-02 | The application shall support **Client mode**: connect to a remote host:port (sender transmits, receiver consumes inbound stream). | MVP |
| FR-03 | The user shall be able to switch between Server and Client modes via the GUI without restarting the application. | MVP |
| FR-03a | If mode, protocol, or role is changed while transport is active, the application shall execute a controlled stop/rebind transition (no abrupt task termination), then apply the new mode/protocol/role with explicit status updates in the GUI. | MVP |
| FR-04 | The application shall support **TCP** and **UDP** protocols, selectable in the GUI. | MVP |
| FR-04a | In server mode, the application shall gracefully handle clients that **connect and disconnect repeatedly** (e.g., Velocity's testConnection → sampleMessages → feed run lifecycle). Disconnections shall not interrupt transmission to other clients or cause errors. | MVP |
| FR-04b | The application shall support a **Sender ⇄ Receiver role toggle** in the GUI. Role is orthogonal to Server/Client mode and TCP/UDP protocol. Default role is **Sender**. | MVP |
| FR-04c | Controls and panels not applicable to the active role shall be **disabled or hidden** (e.g., file preview/rate controls in Receiver role; sink-file controls in Sender role). | MVP |

### 3.2 File Loading & Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-05 | The application shall allow the user to select and load a delimited text file (CSV, TSV, or custom delimiter) via a file browser dialog. | MVP |
| FR-06 | The user shall be able to configure the field delimiter character in the GUI. | MVP |
| FR-07 | The application shall support a configurable header row toggle. When enabled, the first line is treated as field names (used for field selection dropdowns). | MVP |
| FR-08 | The user shall be able to toggle whether the header row is sent to clients. When enabled in server mode, the header shall be sent as the **first message to each newly connected client**. | MVP |
| FR-09 | The application shall display a preview of the loaded file (**first 10 rows**, field count, total line count) in the GUI. During background scan, totals may be provisional and must be clearly labeled as such. Invalid lines shall be highlighted in red with a total discarded count. | MVP |
| FR-10 | The application shall handle files with inconsistent line endings (CRLF, LF). | MVP |
| FR-11 | The application shall support UTF-8 encoded files. | MVP |
| FR-12 | The application shall validate column count consistency on load. Lines with inconsistent column counts shall be **discarded** and logged. | MVP |
| FR-12a | File indexing and validation shall run in a background task and shall not block GUI interaction. | MVP |
| FR-12b | Users shall be able to start transmission before full-file indexing/validation completes. Progress and invalid-line counts shall be finalized when scanning completes. | MVP |
| FR-12c | Delimited parsing shall support RFC 4180-style CSV semantics: quoted fields, escaped quotes, embedded delimiters, and embedded newlines. | MVP |
| FR-12d | Transmission shall perform per-record delimiter/column validation before emit so invalid rows are discarded even if encountered before full background scan completion. | MVP |

### 3.3 Data Transmission

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13 | Each line of the loaded file shall be sent as a discrete message, terminated by a configurable line ending (default: `\n`). | MVP |
| FR-14 | The user shall be able to configure the send rate in **features per second** (1 feature = 1 line). | MVP |
| FR-15 | The GUI shall display both **features/s** and **KB/s** in real time during transmission. | MVP |
| FR-16 | The application shall support **automatic mode**: continuously send lines at the configured rate. | MVP |
| FR-17 | The application shall support **step mode**: send one line per user click (manual advance). | MVP |
| FR-17a | In step mode, the user shall be able to **jump to a specific 1-based data line number** (header excluded; discarded lines excluded from numbering) and send from that point. Out-of-range values shall be rejected with clear feedback. | MVP |
| FR-18 | The application shall support **looping**: when EOF is reached, restart from the first data line. Looping is on by default in automatic mode. | MVP |
| FR-19 | The application shall allow the user to **pause and resume** transmission without dropping connections. | MVP |
| FR-20 | The GUI shall display the current line number, total lines, and a progress indicator during transmission. | MVP |
| FR-20a | In server broadcast mode, automatic transmission shall **pause when zero clients are connected** and resume when at least one client reconnects. | MVP |
| FR-20b | While paused due to zero connected clients, the transmission line pointer shall not advance. | MVP |
| FR-20c | The user shall be able to **change send rate during active transmission** without restarting the application; the new rate shall take effect by the next scheduling interval. | MVP |
| FR-20d | The user shall be able to **load/swap the input file without restarting**. If swap is applied while sending, the switch occurs at the next message boundary, resets to line 1 of the new file, and preserves active network connections. | MVP |
| FR-20e | On file swap during active send, per-client output ordering shall remain generation-safe: a client must not receive interleaved records from old and new files. Default behavior is to drain queued old-file records before new-file records are emitted. | MVP |
| FR-20f | If `send_header` is enabled and a file swap occurs during active send, currently connected clients shall receive the new file header once before the first new-file data record. | MVP |
| FR-21 | Post-MVP: Support **original-rate mode** — send lines at the rate implied by the timestamp deltas in the original data. | Post-MVP |
| FR-22 | Post-MVP: Support sending a **subset of lines** (start/end line, first N lines). | Post-MVP |

### 3.4 Timestamp Field Handling

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-23 | The user shall be able to designate a field (by name from header, or by **1-based column index**) as the **timestamp field** via a GUI dropdown. | MVP |
| FR-24 | The user shall be able to select the timestamp format from: **ISO 8601, epoch milliseconds, epoch seconds (integer), epoch seconds (fractional)**. | MVP |
| FR-25 | When timestamp replacement is enabled, the application shall replace the original timestamp with a **current-time-based value** at send time, preserving the relative offset between consecutive rows. | MVP |
| FR-26 | The user shall be able to **disable** timestamp replacement (send raw file data). | MVP |
| FR-27 | Post-MVP: Auto-detect timestamp format from the data. | Post-MVP |

### 3.5 Network Configuration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-28 | The user shall be able to configure the **TCP/UDP port** (server: listen port; client: destination port). | MVP |
| FR-29 | In client mode, the user shall be able to configure the **destination host/IP**. | MVP |
| FR-30 | In server mode, the application shall allow configuring the **bind address** (default: `0.0.0.0`). | MVP |
| FR-31 | In TCP client mode, the application shall **auto-reconnect** on disconnect with exponential backoff. The GUI shall display reconnect status and total reconnect count. | MVP |
| FR-32 | In TCP server mode, the application shall monitor per-client write buffers and **disconnect slow clients** that cannot keep up. The GUI shall display blocking status and which clients were disconnected. | MVP |
| FR-32a | Backpressure management shall use per-client outbound queues with configurable high/low watermarks and a hard queue-cap in bytes. | MVP |
| FR-32b | A client shall be marked blocked when it crosses the high watermark, cleared when below the low watermark, and disconnected when blocked duration exceeds timeout or hard-cap is reached. | MVP |
| FR-32c | In UDP reply-to-senders mode, recipient cache maintenance shall enforce TTL expiry, maximum entry cap, periodic cleanup, and deterministic eviction policy (default: LRU). | MVP |
| FR-33 | The application shall support configurable **connection timeout** and **send timeout** values, both defaulting to **10 seconds**. | MVP |
| FR-34 | Post-MVP: Optional **TLS/SSL** support with certificate configuration. | Post-MVP |

### 3.6 Logging & Reporting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-35 | The application shall log all connection events (connect, disconnect, reconnect, slow client disconnect) in **JSON structured format**. | MVP |
| FR-36 | The application shall log transmission statistics: features sent, bytes sent, elapsed time, current rate (feat/s and KB/s). | MVP |
| FR-37 | The application shall write JSON logs to a configurable log file with **log rotation** (default: 10 MB max, configurable) and configurable retention count (default: 5 rotated files). | MVP |
| FR-38 | The GUI shall provide an on-demand log panel that loads and refreshes JSON log entries only when the user clicks **Load** or **Refresh**. No automatic live tailing/streaming is required. | MVP |
| FR-39 | Log verbosity shall be configurable (DEBUG, INFO, WARN, ERROR). | MVP |
| FR-40 | Post-MVP: Dedicated on-demand log viewer UI component with filtering, search, and export. | Post-MVP |

### 3.7 Configuration Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-41 | The application shall support saving the current configuration to a **JSON file**. | MVP |
| FR-42 | The application shall support loading a previously saved JSON configuration file, populating all GUI fields. | MVP |
| FR-43 | The application shall provide sensible defaults for all configuration values. | MVP |
| FR-44 | The application shall **auto-load the last-used configuration** on startup. | MVP |
| FR-45 | Configuration files shall include an integer **schema_version** field. | MVP |
| FR-46 | On config load, the application shall migrate known older schema versions; unknown or incompatible versions shall be rejected and replaced with defaults while preserving the original file and surfacing a clear warning. | MVP |
| FR-47 | The application shall not auto-overwrite incompatible configuration files; migrated configurations are persisted only when the user explicitly saves. | MVP |

### 3.8 Validation & Test Automation

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-48 | The project shall include a mandatory **automated integration test suite** that exercises repeated TCP connect/disconnect/reconnect storms (including Velocity-like lifecycle churn). | MVP |
| FR-49 | The project shall include a mandatory **automated integration test suite** for slow-client churn and backpressure behavior (blocked state, watermark recovery, disconnect policy). | MVP |
| FR-50 | The project shall include a mandatory **automated soak test suite** for large-file streaming and long-running resource stability (memory/descriptor growth, reconnect stability, no deadlock). | MVP |
| FR-51 | Manual socket tools (e.g., netcat/telnet) may be used for exploratory smoke checks, but they are **non-gating** and not a substitute for automated suites. | MVP |
| FR-52 | MVP release quality gate: unit tests, integration tests, and soak tests must pass before merge to release branch. | MVP |
| FR-53 | Automated suites shall implement the named MVP matrix scenarios in Section **5.5.1** (`TM-INT-01` through `TM-SOAK-03`). | MVP |
| FR-54 | Each matrix scenario shall define setup profile, duration, and numeric pass/fail thresholds; CI shall fail when any threshold is violated. | MVP |
| FR-55 | The project shall provide a standalone `scripts/preflight.py` command that exits non-zero when prerequisites fail and prints actionable setup guidance (Python version, active virtual environment, tkinter/Tk availability). | MVP |

### 3.9 Receiver Role

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-56 | In **Receiver role, Server mode (TCP)**, the application shall bind and accept inbound TCP connections and read framed records from every connected peer concurrently. | MVP |
| FR-57 | In **Receiver role, Client mode (TCP)**, the application shall connect outbound to a configured host:port and read framed records from the remote peer. Auto-reconnect with exponential backoff (shared policy with sender client, FR-31) shall apply. | MVP |
| FR-58 | In **Receiver role, Server mode (UDP)**, the application shall bind to a configured port (optionally joining a multicast group) and consume inbound datagrams from any source. | MVP |
| FR-59 | In **Receiver role, Client mode (UDP)**, the application shall bind a local ephemeral port, optionally send a configurable "hello" datagram to the remote host:port to register with publishers, and consume inbound datagrams from that peer. | MVP |
| FR-60 | The receiver shall frame TCP streams using the configured **record separator** (default `\n`, options `\n`, `\r\n`, raw-chunk). For UDP, each datagram is one record. | MVP |
| FR-61 | Records larger than the configured **max record bytes** (default 1 MiB) shall be truncated at the cap, emitted to the sink with a truncation flag, and logged at WARN. | MVP |
| FR-62 | The receiver shall expose live **receive statistics** in the GUI: total records received, total bytes received, current records/s and KB/s, connected peer count (server mode) or connection state (client mode), per-peer last-seen timestamps. | MVP |
| FR-63 | The receiver shall support an **optional sink-to-file** feature, disabled by default. When enabled, every received record is appended to the configured sink file. | MVP |
| FR-64 | The sink file format shall be user-selectable between **delimited passthrough** (raw received payload followed by the configured record separator) and **JSON Lines** (one JSON object per line containing at minimum `ts` ISO 8601 UTC, `src` peer address, `bytes_len` integer, `payload` UTF-8 string, and `truncated` boolean; non-UTF-8 payloads are base64-encoded and marked with `"encoding":"base64"`). | MVP |
| FR-65 | The sink file shall support **rotation** by size with a configurable max bytes (default 100 MB) and configurable backup count (default 5). Rotation shall not drop in-flight records. | MVP |
| FR-66 | The user shall be able to **enable/disable sink writing**, **switch sink format**, and **change sink file path** at runtime without restarting the application. Transitions take effect at the next record boundary. | MVP |
| FR-67 | The GUI shall display sink-file status: enabled/disabled, current path, current file size, total bytes written, and rotation count. | MVP |
| FR-68 | The receiver shall apply **backpressure** when the sink writer cannot keep up: inbound TCP reads are paused (per-peer) when the sink write queue exceeds a configurable high watermark and resumed below the low watermark. For UDP, excess datagrams shall be dropped and counted. | MVP |
| FR-69 | All receiver connection and data events (connect, disconnect, record received summary at DEBUG, truncation, sink rotation, sink errors, UDP drops) shall be emitted to the JSON structured log. | MVP |
| FR-70 | The receiver shall cleanly stop on role switch, application shutdown, and window close, flushing and closing the sink file without data loss for successfully read records. | MVP |
| FR-71 | Automated tests shall cover receiver role end-to-end behavior for each of the four role+mode combinations, sink-file correctness (both formats), rotation, runtime enable/disable, and backpressure behavior. | MVP |

---

## 4. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | The application shall run on Windows 10+ and common Linux distributions (Ubuntu 20.04+, RHEL 8+) with Python 3.10+ installed. | MVP |
| NFR-02 | The application shall **stream** files line-by-line. No file size limit; memory usage shall remain bounded regardless of file size. | MVP |
| NFR-03 | The application shall support at least **50 simultaneous client connections** in server mode. | MVP |
| NFR-04 | The application shall provide a **GUI** as its primary interface. The engine shall be decoupled to allow future CLI use. | MVP |
| NFR-05 | The application shall be distributed as **source only** with a documented **venv-first** setup workflow (create/activate virtual environment, `pip install -e .`, then `python -m tcp_sim`). | MVP |
| NFR-06 | The application shall shut down gracefully on window close or SIGINT/SIGTERM, closing all connections cleanly. | MVP |
| NFR-07 | The application shall not crash or hang when a client disconnects unexpectedly. | MVP |
| NFR-08 | The GUI shall remain responsive during file loading, transmission, and high connection counts. All I/O shall be async. | MVP |
| NFR-09 | On startup and via standalone `scripts/preflight.py`, the application shall run runtime preflight checks for Python version, active virtual environment, and tkinter/Tk availability; missing prerequisites shall produce actionable setup guidance instead of stack traces. | MVP |
| NFR-10 | Large-file indexing/validation must execute in background without blocking startup; UI controls remain usable while scanning is in progress. | MVP |
| NFR-11 | Automated test suites (unit + integration + soak) shall execute in CI for pull requests and release branches, with deterministic pass/fail reporting. | MVP |
| NFR-12 | Soak test baseline shall run for at least **30 minutes** in CI and assert stable resource behavior (no unbounded memory/file-descriptor growth and no scheduler deadlock). | MVP |
| NFR-13 | Local development and manual execution instructions shall assume an activated virtual environment; global-site-package installs are not the recommended workflow. | MVP |

---

## 5. Architecture & Design

### 5.1 Technology Stack

**Decided:** Python 3.10+ with `asyncio` for async TCP/UDP handling.

**GUI Framework:** tkinter (ships with Python stdlib). No additional GUI dependencies. The UI is functional, not pretty — this is an internal engineering tool, not a consumer product.

**Distribution:** Source-only. Users clone the repo and run with Python 3.10+. Dependencies managed via `requirements.txt` or `pyproject.toml`. No theming or dark mode.

**Key Libraries (all stdlib except where noted):**
- `asyncio` — TCP/UDP server and client
- `tkinter` — GUI (stdlib, ships with Python)
- `json` — Config files, structured logging
- `csv` — File parsing (with manual fallback for custom delimiters)
- `pathlib` — Cross-platform path handling
- `logging` — Structured JSON logging via custom formatter
- `threading` — Bridge between tkinter main thread and asyncio event loop

### 5.2 High-Level Components

```
┌──────────────────────────────────────────────────────────┐
│                       GUI Layer                           │
│  ┌────────────┐ ┌──────────┐ ┌────────────┐ ┌─────────┐ │
│  │ Mode/Config │ │ File     │ │ Transport  │ │ Stats/  │ │
│  │ Panel       │ │ Preview  │ │ Controls   │ │ Log View│ │
│  └────────────┘ └──────────┘ └────────────┘ └─────────┘ │
├──────────────────────────────────────────────────────────┤
│               Simulator Engine                            │
│  ┌───────────┐  ┌────────────┐  ┌────────────┐          │
│  │ File       │  │ Send       │  │ Timestamp  │          │
│  │ Reader     │  │ Scheduler  │  │ Rewriter   │          │
│  │ (streaming)│  │ (feat/s)   │  │            │          │
│  └───────────┘  └────────────┘  └────────────┘          │
├──────────────────────────────────────────────────────────┤
│             Transport Layer                               │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐  │
│  │ TCP Server   │ │ TCP Client   │ │ UDP Server/Client│  │
│  │ (listen/     │ │ (connect/    │ │ (send/listen)    │  │
│  │  broadcast)  │ │  reconnect)  │ │                  │  │
│  └──────────────┘ └──────────────┘ └──────────────────┘  │
├──────────────────────────────────────────────────────────┤
│          Connection Manager                               │
│  - Track connected clients (server mode)                  │
│  - Monitor per-client backpressure / write buffer         │
│  - Disconnect slow clients with notification              │
│  - Auto-reconnect with backoff (client mode)              │
│  - Reconnect counter and status                           │
├──────────────────────────────────────────────────────────┤
│              Logging / Stats Engine                        │
│  - JSON structured log output to file                     │
│  - Features/sec, KB/s, total sent, elapsed time           │
│  - Connection events, reconnect count                     │
│  - Slow client disconnect events                          │
└──────────────────────────────────────────────────────────┘
```

### 5.2.1 GUI Layout (Conceptual)

```
┌─────────────────────────────────────────────────────────┐
│  TCP Simulator                                    [—][□][×] │
├────────────────────────┬────────────────────────────────┤
│  Mode: [Server ▼]      │  File: [data.csv] [Browse...]  │
│  Protocol: [TCP ▼]     │  Delimiter: [, ▼] Header: [✓]  │
│  Host: [0.0.0.0  ]     │  Timestamp Field: [3 ▼]        │
│  Port: [5565     ]     │  Timestamp Format: [ISO 8601 ▼]│
├────────────────────────┴────────────────────────────────┤
│  File Preview (first 10 rows)                            │
│  ┌──────────────────────────────────────────────────────┐│
│  │ lat     | lon      | timestamp           | id       ││
│  │ 34.0522 | -118.243 | 2026-04-02T10:00:00 | truck-01 ││
│  │ 34.0525 | -118.244 | 2026-04-02T10:00:05 | truck-01 ││
│  │ ...                                                  ││
│  └──────────────────────────────────────────────────────┘│
├──────────────────────────────────────────────────────────┤
│  Rate: [10  ] feat/s   [▶ Start] [⏸ Pause] [⏹ Stop]    │
│  [  ] Loop at EOF      [ Step ▶| ]                       │
├──────────────────────────────────────────────────────────┤
│  Status:                                                  │
│  ● Listening on 0.0.0.0:5565                             │
│  Connected clients: 3  |  Line: 1,247 / 50,000          │
│  Rate: 10.1 feat/s  |  42.3 KB/s  |  Elapsed: 00:02:04  │
│  ⚠ Blocked: 1 client  |  Disconnected (slow): 1          │
├──────────────────────────────────────────────────────────┤
│  Log File: tcp-sim.log                  [Load] [Refresh]  │
│  Last Loaded: 10:24:31                  Entries: 2,000    │
│  {"ts":"...","event":"client_connect","addr":"10.0.1.5"} │
│  {"ts":"...","event":"send","line":1247,"bytes":87}      │
│  {"ts":"...","event":"slow_client","addr":"10.0.1.8"...} │
└──────────────────────────────────────────────────────────┘
```

### 5.3 Key Design Decisions

#### GUI ↔ Engine Separation
The GUI must not contain business logic. The simulator engine should be fully functional without a GUI, communicating via an event/callback interface. This enables:
- Future CLI mode without rewriting the engine
- Testability (unit test the engine without GUI)
- Clean async boundary (engine runs in asyncio, GUI runs in its event loop)

The recommended pattern is a **controller** layer that bridges the GUI thread and the asyncio event loop using thread-safe queues or `asyncio.run_coroutine_threadsafe()`.

#### Protocol Support
Both TCP and UDP are supported. UDP has no concept of "connections" so:
- **UDP Server mode:** Two recipient discovery options, user-selectable in the GUI:
  - **Multicast:** Send datagrams to a configured multicast group address.
  - **Reply to senders:** Send datagrams to all addresses that have previously sent a packet to our listen port. Default recipient cache TTL is **300 seconds** with a cap of **256 entries**, cleanup every **30 seconds**, and **LRU** eviction when full; all values are configurable.
- **UDP Client mode:** Send datagrams to a configured host:port. No connection, no reconnect logic needed.

UDP mode should clearly indicate in the UI that delivery is not guaranteed.

#### Message Framing
Each CSV line is sent as a newline-terminated string. The receiver is expected to parse on newline boundaries. The line terminator sent over the wire should be configurable (`\n`, `\r\n`, or none).

#### Server Mode: Broadcast
All connected clients receive the same line at the same time. A client that connects mid-stream joins at whatever line is current. This is simpler and matches the testing use case.

**Velocity lifecycle handling:** In server mode, clients (particularly Velocity) will connect and disconnect multiple times during feed setup (testConnection, sampleMessages, feed run). The server must:
- Accept and cleanly release connections without error messages cluttering the log
- Continue broadcasting to remaining clients when one disconnects
- Optionally re-send the header row to newly connected clients (if "send header" is enabled)
- Pause automatic broadcast progression while zero clients are connected; resume when a client reconnects
- Keep line pointer stable while paused (no implicit advancement)
- Not reset the line position when a client disconnects and reconnects
- Log connect/disconnect events at INFO level (not WARN/ERROR — these are expected)

#### Header Row Handling
- The first line of the CSV is assumed to be a header by default.
- The header is used for field name display in the GUI (e.g., timestamp field dropdown).
- The user can toggle whether the header is sent to clients as the first message.
- When "send header" is enabled, the header should be sent as the **first message to each new client connection**. This is critical for Velocity's sampleMessages phase — Velocity uses the first few messages to derive the data schema, and the header row helps it map field names correctly.
- If "no header" is configured, the first line is treated as data.

#### CSV Validation
On file load, check column count consistency using CSV parsing rules that honor quoting and escaping semantics. Lines with inconsistent column counts are **discarded** (not sent) and logged with a warning. The GUI file preview should flag invalid lines.

During transmission, validate each candidate row before emit so invalid rows discovered ahead of completed background scan are still discarded.

#### File Reading Strategy
Stream the file line-by-line using a buffered reader. Do not load the entire file into memory. For looping, seek back to the start of data (after header row, if any).

Use a progressive background scan for total-line and invalid-line accounting:
1. Start scan asynchronously at file load.
2. Allow transmission start before scan completion.
3. Mark total/invalid counts as provisional until scan completes.
4. Publish periodic scan progress updates to the GUI.

Runtime file swap behavior:
1. User selects and validates new file in background.
2. On apply, perform atomic source switch at next message boundary.
3. Preserve per-client generation ordering (no old/new interleaving within one client stream); default behavior is to drain old-file queued records first.
4. If `send_header` is enabled, enqueue the new file header once for each currently connected client before first new-file data row.
5. Reset active line pointer to first data line of new file.
6. Keep active transport sessions connected.

#### Backpressure & Slow Clients
Use per-client outbound queues and watermarks. Default thresholds (configurable):
- High watermark: **256 KB**
- Low watermark: **128 KB**
- Hard cap: **512 KB**

If a client's queue exceeds the high watermark:
1. Log the blocking status (JSON structured log).
2. Show blocking indicator in the GUI.
3. If the client cannot drain within the configured timeout (default: **10 seconds**), **disconnect** it.
4. Log the disconnection with client address and reason.
5. Show disconnected slow clients in the GUI status area.

Clear blocked status only after queue depth falls below the low watermark.
Disconnect immediately if hard cap is exceeded.

Do **not** slow down the broadcast for other clients because one client is slow.

#### Client Mode: Auto-Reconnect
On disconnect, automatically attempt to reconnect with exponential backoff (1s, 2s, 4s, 8s, ... max **30 seconds**, configurable). Display:
- Reconnection attempts in progress
- Total reconnect count
- Last disconnect reason

Data transmission pauses during reconnection and resumes from the current line (not from the beginning) once reconnected.

#### Timestamp Rewriting
1. Parse the designated timestamp field from the **first data row** as T₀.
2. For each subsequent row, calculate `offset = row_timestamp - T₀`.
3. At send time, compute `new_timestamp = now() + offset`.
4. Replace the field value in the outgoing line with the new timestamp formatted per the configured pattern.
5. Supported formats (MVP): ISO 8601, epoch milliseconds, epoch seconds (integer), epoch seconds (fractional).

Clock/timezone policy:
- Normalize parsed timestamps to **UTC** internally.
- Use monotonic time for scheduler delays to avoid wall-clock jumps affecting send cadence.
- Use wall-clock UTC only when constructing replacement timestamps.

This preserves the relative timing between events while anchoring them to the current wall clock.

#### Rate Control
- Primary unit: **features per second** (1 feature = 1 CSV data line).
- The GUI displays both features/s and KB/s in real time.
- Rate changes during active send are supported and take effect without application restart.
- Post-MVP: **original-rate mode** — use timestamp deltas between consecutive rows to determine send timing.

#### Log Viewing Behavior
- The simulator writes JSON logs to file continuously.
- The GUI log panel is **on-demand only**: logs are loaded/refreshed when the user requests it.
- No automatic live log streaming/tailing in MVP (or post-MVP by default).
- On-demand refresh reduces tkinter UI update pressure during high-throughput sends.

#### Receiver Role (Sender ⇄ Receiver Toggle)
The application supports a **Receiver role** orthogonal to Server/Client mode and TCP/UDP protocol. The role is selected via a top-level GUI toggle and drives which engine pipeline is active:

- **Sender pipeline:** file reader → scheduler → timestamp rewriter → transport.
- **Receiver pipeline:** transport → frame splitter → (optional) sink writer.

Receiver behavior by transport combination:
- **TCP Server:** bind and `accept()` loop; each accepted peer runs an independent read loop that splits the byte stream on the configured record separator. Peer connect/disconnect churn is handled the same way as sender Server mode (non-error, lifecycle-normal).
- **TCP Client:** connect to a configured host:port; read until EOF or error; apply the shared auto-reconnect policy with exponential backoff (FR-31).
- **UDP Server:** bind a datagram socket (optionally join a multicast group). Each datagram is one record. Source address is recorded for stats and for the JSONL `src` field.
- **UDP Client:** bind an ephemeral port, optionally send a configurable "hello" datagram to the remote host:port to register with publishers that key off sender address, then read datagrams from that peer.

Framing:
- TCP record separator is shared with the sender (`\n` default, `\r\n`, or raw-chunk). Raw-chunk emits whatever bytes each read returns as one record (useful for binary/pre-framed streams).
- Records are capped at `receiver_max_record_bytes` (default **1 MiB**); oversize records are truncated, flagged with `truncated=true` in JSONL sink and logged WARN.

Sink file (optional):
- **Disabled by default.** Receiver can be used purely for metrics/observation.
- Two formats, user-selectable at runtime:
  - **Delimited passthrough:** append raw payload bytes followed by the configured record separator. Preserves byte fidelity for replay through the sender role.
  - **JSON Lines:** append one JSON object per line: `{"ts":"2026-04-17T12:34:56.789Z","src":"10.0.1.5:54321","bytes_len":87,"payload":"...","truncated":false}`. Non-UTF-8 payloads set `"encoding":"base64"` and base64-encode the payload.
- **Rotation:** size-based with configurable max bytes (default 100 MB) and backup count (default 5). Shares the same rotation primitives as JSON logs.
- **Runtime reconfiguration:** enable/disable, format swap, and path change take effect at the next record boundary with no connection drop.
- **Backpressure:** sink writer runs on a bounded queue. TCP receivers pause their per-peer read loop when the sink queue exceeds its high watermark and resume below the low watermark; this creates natural TCP backpressure to the sender. UDP drops excess datagrams (and counts them) because UDP has no flow control.

Stats / GUI:
- Receiver role exposes records/s, KB/s, total records, total bytes, peer count (server) or connection state (client), per-peer last-seen, sink state (enabled/path/size/rotations), UDP drop count, and truncation count.
- Sender-only controls (rate, step, loop, file preview, timestamp rewrite) are disabled/hidden in Receiver role. Receiver-only controls (sink path/format/enable, max record bytes) are disabled/hidden in Sender role.

#### Environment Preflight
- Provide a standalone script at `scripts/preflight.py` that users can run before first launch.
- The script and application startup must use the same validation logic to avoid drift.
- Minimum checks: Python version compatibility (3.10+), active virtual environment, tkinter/Tk import availability.
- Preflight failures must return non-zero exit code and actionable remediation text.

### 5.4 Configuration

Configuration is saved/loaded as **JSON** files. The GUI provides a "Save Config" / "Load Config" button pair.

The config file stores all user-configurable settings:

```json
{
  "schema_version": 1,
  "mode": "server",
  "protocol": "tcp",
  "host": "0.0.0.0",
  "port": 5565,
  "file": "data.csv",
  "delimiter": ",",
  "has_header": true,
  "send_header": true,
  "rate_features_per_second": 10,
  "loop": true,
  "timestamp_field": 3,
  "timestamp_format": "iso8601",
  "replace_timestamp": true,
  "line_ending": "\n",
  "log_file": "tcp-sim.log",
  "log_level": "INFO",
  "connect_timeout_seconds": 10,
  "send_timeout_seconds": 10,
  "slow_client_timeout_seconds": 10,
  "reconnect_max_backoff_seconds": 30,
  "client_queue_high_watermark_bytes": 262144,
  "client_queue_low_watermark_bytes": 131072,
  "client_queue_hard_cap_bytes": 524288,
  "log_rotation_max_bytes": 10485760,
  "log_rotation_backup_count": 5,
  "udp_recipient_mode": "reply_to_senders",
  "udp_recipient_cache_ttl_seconds": 300,
  "udp_recipient_cache_max_entries": 256,
  "udp_recipient_cache_cleanup_interval_seconds": 30,
  "udp_recipient_cache_eviction_policy": "lru",
  "role": "sender",
  "receiver": {
    "record_separator": "\n",
    "max_record_bytes": 1048576,
    "sink_enabled": false,
    "sink_format": "jsonl",
    "sink_path": "received.jsonl",
    "sink_rotation_max_bytes": 104857600,
    "sink_rotation_backup_count": 5,
    "sink_queue_high_watermark_bytes": 1048576,
    "sink_queue_low_watermark_bytes": 524288,
    "udp_client_hello_bytes": ""
  }
}
```

The GUI is the primary interface. All settings are configurable through the GUI. A future CLI mode could consume the same JSON config files.

Before loading user config, run startup preflight checks for Python runtime and tkinter/Tk availability so missing dependencies fail with actionable guidance.

#### 5.4.1 Config Migration Policy
Config compatibility follows a hybrid policy designed for safety and convenience in a standalone tool:

1. If `schema_version` matches the current version, load normally.
2. If the file is from an older known schema version, apply deterministic in-memory migration steps and continue.
3. If migration fails, or if the version is unknown/newer/incompatible, reject the file, preserve it unchanged on disk, load defaults, and surface a clear warning in GUI and logs.

The application should never silently mutate or overwrite an incompatible config file.

### 5.5 Test Strategy

Testing follows a required automation-first approach:

1. **Unit tests**
- Engine logic (reader, scheduler, timestamp rewrite, config migration).
- Fast and deterministic; run on every PR.

2. **Integration tests (mandatory)**
- Reconnect storm scenarios: repeated connect/disconnect cycles matching Velocity's testConnection/sampleMessages/feed-run behavior.
- Slow-client churn scenarios: multiple clients with mixed throughput validating watermark transitions and disconnect logic.

3. **Soak tests (mandatory)**
- Large-file streaming for long duration (minimum 30 minutes in CI).
- Assertions for resource stability and liveness (no deadlocks, reconnect loop remains healthy).

Manual socket-tool checks (netcat/telnet) are optional diagnostics only and do not satisfy release criteria.

### 5.5.1 MVP Test Matrix

| ID | Suite | Scenario | Setup Profile | Duration | Pass/Fail Criteria |
|----|-------|----------|---------------|----------|--------------------|
| TM-INT-01 | Integration | **Server reconnect storm (Velocity lifecycle)** | 20 concurrent synthetic clients repeating `testConnection -> sampleMessages -> feed run` cycle for 200 rounds. Broadcast mode, header-on-connect enabled. | >= 15 min | 1) No process crash/deadlock. 2) >= 99.5% connection-attempt success. 3) No leaked active client sessions after cycle completion. 4) Memory growth <= 15% after 5-min warmup. |
| TM-INT-02 | Integration | **Client reconnect storm (flapping upstream server)** | Simulator in client mode against flapping TCP server (`5s up / 5s down`) for 300 transitions. `reconnect_max_backoff_seconds` set to 5 for determinism. | >= 20 min | 1) Reconnect counter increments for each outage. 2) Sending resumes within `max_backoff + 1s` after server recovery. 3) No malformed/partial line framing after reconnect. 4) No uncaught exceptions. |
| TM-INT-03 | Integration | **Slow-client churn and backpressure** | Server mode with 50 clients: 40 normal consumers + 10 throttled consumers (<= 1 KB/s). Send rate >= 200 features/s with ~512-byte lines. | >= 20 min | 1) Slow clients enter blocked state and disconnect within `slow_client_timeout_seconds + 2s`. 2) Normal clients remain connected and continue receiving data. 3) Per-client queues never exceed hard cap. 4) No global broadcast stall caused by slow clients. |
| TM-SOAK-01 | Soak | **Large-file streaming stability** | Server mode, looping enabled, input file >= 5 GB, 10 normal clients. | >= 30 min in CI (>= 2 h local extended) | 1) No crash/deadlock. 2) RSS memory growth <= 15% after warmup (rolling 10-min window). 3) File/socket handle growth is non-monotonic (delta <= +5 after warmup). 4) Throughput remains within +/-10% of configured rate excluding planned pause periods. |
| TM-SOAK-02 | Soak | **UDP reply-to-senders cache stability** | UDP server in reply-to-senders mode with churned sender endpoints (>= 2,000 unique address:port pairs). | >= 30 min | 1) Recipient cache size never exceeds configured cap. 2) Expired recipients removed within `cleanup_interval + 5s`. 3) Overflow eviction follows configured policy (`lru`). 4) No unbounded memory growth. |
| TM-INT-04 | Integration | **Receiver role end-to-end (all 4 role+mode combos)** | Drive each of Receiver TCP-Server, Receiver TCP-Client, Receiver UDP-Server, Receiver UDP-Client against a scripted sender emitting known payloads (10k records, 200 records/s). Test both sink formats (delimited, JSONL) and sink-off mode. | >= 10 min per combo | 1) All records accounted for (received count == sent count minus intentional UDP losses). 2) Sink file byte/record counts match expectations for each format. 3) Truncation flag set correctly for oversize records. 4) Runtime sink enable/disable/path-swap produces no dropped records for TCP. |
| TM-SOAK-03 | Soak | **Receiver sink rotation and backpressure stability** | Receiver TCP-Server, JSONL sink enabled, 20 senders at aggregate >= 500 records/s, artificial slow disk via small sink queue watermarks to force rotation and backpressure. | >= 30 min | 1) Sink file rotates at configured threshold with correct backup count retained. 2) Per-peer read-pause activates above high watermark and clears below low watermark. 3) No memory or file-descriptor growth beyond warmup. 4) No data loss on TCP peers; UDP drop counter (if any UDP cross-traffic) is monotonic and bounded. |

### 5.5.2 CI Gate Policy

1. PR gate must run: unit + integration + soak baseline profiles.
2. Release-branch gate must run: full unit + integration + soak profiles.
3. A single failed matrix scenario blocks merge.
4. Manual socket-tool checks are informational only and cannot override failing automated gates.

### 5.6 Proposed Project Structure

```
tcp-server-simulator/
├── docs/
│   └── design-and-requirements.md
├── src/
│   └── tcp_sim/
│       ├── __init__.py
│       ├── main.py                  # Entry point, launches GUI
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── file_reader.py       # Streaming CSV reader, validation
│       │   ├── scheduler.py         # Rate control, step/auto/loop logic
│       │   ├── timestamp.py         # Timestamp parsing and rewriting
│       │   ├── simulator.py         # Orchestrates reader + scheduler + transport (sender)
│       │   ├── receiver.py          # Orchestrates transport + framer + sink (receiver)
│       │   ├── framer.py            # Record-separator framing for TCP receive
│       │   └── sink_writer.py       # Delimited passthrough + JSONL sink with rotation
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── base.py                       # Shared socket lifecycle, bind/connect, shutdown helpers
│       │   ├── tcp_server_sender.py          # TCP server, broadcast, backpressure, slow-client disconnect
│       │   ├── tcp_server_receiver.py        # TCP server, accept loop, per-peer read/frame, sink backpressure
│       │   ├── tcp_client_sender.py          # TCP client, auto-reconnect, outbound send queue
│       │   ├── tcp_client_receiver.py        # TCP client, auto-reconnect, inbound read/frame
│       │   ├── udp_server_sender.py          # UDP listener/sender (multicast or reply-to-senders)
│       │   ├── udp_server_receiver.py        # UDP listener, datagram-per-record consume
│       │   ├── udp_client_sender.py          # UDP client sender
│       │   ├── udp_client_receiver.py        # UDP client (bind ephemeral, optional hello, consume)
│       │   └── connection_manager.py         # Track peers, slow-client detection, reconnect state
│       ├── config/
│       │   ├── __init__.py
│       │   └── config.py            # JSON config load/save, defaults
│       ├── logging/
│       │   ├── __init__.py
│       │   └── json_logger.py       # JSON structured logging
│       └── gui/
│           ├── __init__.py
│           ├── app.py               # Main window
│           ├── config_panel.py      # Mode, host, port, protocol settings
│           ├── file_panel.py        # File selection, preview, field config
│           ├── control_panel.py     # Start/stop/pause/step, rate control
│           ├── status_panel.py      # Stats, connection list, blocking indicators
│           └── log_panel.py         # On-demand JSON log load/refresh
├── tests/
│   ├── unit/
│   │   ├── test_file_reader.py
│   │   ├── test_scheduler.py
│   │   ├── test_timestamp.py
│   │   └── test_config.py
│   ├── integration/
│   │   ├── test_tcp_server_reconnect_storm.py
│   │   ├── test_tcp_client_reconnect_storm.py
│   │   ├── test_slow_client_churn_backpressure.py
│   │   ├── test_udp_reply_to_senders_cache.py
│   │   ├── test_receiver_tcp_server.py
│   │   ├── test_receiver_tcp_client.py
│   │   ├── test_receiver_udp.py
│   │   └── test_receiver_sink_formats_and_rotation.py
│   └── soak/
│       └── test_large_file_streaming_stability.py
├── scripts/
│   └── preflight.py                # Standalone environment readiness check
├── configs/
│   └── example.json                 # Example config file
├── data/
│   └── sample.csv                   # Sample data file for testing
├── requirements.txt
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## 6. Original Spec Gaps (Now Addressed)

The following gaps from the original copilot-instructions have been resolved in this document. Kept here for traceability.

| Gap | Resolution |
|-----|-----------|
| No technology stack | Python 3.10+ (Q1) |
| No message framing | Configurable line terminator: `\n`, `\r\n`, or none (FR-13) |
| No encoding spec | UTF-8 (FR-11) |
| No broadcast semantics | Broadcast mode, late joiners get current line (Q4) |
| No header row handling | Configurable: detect header, toggle sending to clients (FR-07, FR-08) |
| No reconnection logic | Auto-reconnect with backoff, reconnect counter in GUI (FR-31) |
| No pause/resume | Supported (FR-19) |
| No progress indication | GUI displays line number, total, feat/s, KB/s (FR-20, FR-15) |
| No max connection limit | Soft limit of 50 (NFR-03), slow clients disconnected (FR-32) |
| No TLS/SSL | Deferred to post-MVP, architecture accommodates it (FR-34) |
| No send-header option | Configurable (FR-08) |
| No config file support | JSON config save/load (FR-41, FR-42) |
| Logging undefined | JSON structured logging to file + GUI log panel (FR-35 through FR-40) |
| Rate unit ambiguous | Features/second with KB/s display (FR-14, FR-15) |
| No explicit readiness command | Standalone `scripts/preflight.py` plus startup preflight checks (FR-55, NFR-09) |
| No receive-side support | Sender/Receiver role toggle with optional delimited or JSONL sink file (FR-04b, FR-56 through FR-71) |

---

## 7. Risk Register & Cautions

### Implementation Risks

1. **GUI and asyncio concurrency boundaries**
- Risk: UI freezes, race conditions, or deadlocks when crossing thread/event-loop boundaries.
- Mitigation: enforce controller boundary + thread-safe queues; keep GUI updates batched and periodic; ensure cancellation-aware shutdown paths.
- Verification: stress tests with rapid start/stop/pause and reconnect storms.

2. **Large-file indexing behavior**
- Risk: slow scans can appear as hangs or produce confusing counters.
- Mitigation: progressive background scan with clearly labeled provisional totals and non-blocking controls.
- Verification: multi-GB file smoke tests with immediate send-start while scan is in progress.

3. **Backpressure under fan-out load**
- Risk: one slow client degrades all clients or causes unbounded memory growth.
- Mitigation: per-client queues with high/low watermarks, hard-cap disconnects, and blocked-state visibility.
- Verification: soak test with 50 clients including intentionally slow consumers.

4. **UDP recipient-cache correctness**
- Risk: stale endpoints, cache growth, and noisy delivery behavior in reply-to-senders mode.
- Mitigation: TTL expiry, entry cap, periodic cleanup, and deterministic eviction policy (LRU).
- Verification: long-running UDP tests with churned sender IP/port pairs.

5. **Timestamp correctness across clocks and formats**
- Risk: replay drift from timezone ambiguity or wall-clock changes.
- Mitigation: UTC normalization for parsed timestamps and monotonic clock for scheduler delays.
- Verification: test vectors for epoch/int/fractional/ISO timestamps across timezone boundaries.

6. **Config compatibility across versions**
- Risk: startup failures or silent misconfiguration when config schema evolves.
- Mitigation: `schema_version`, deterministic migrations for known versions, safe fallback defaults for incompatible versions, no automatic overwrite.
- Verification: migration tests from each historical schema fixture.

7. **Source-only environment drift**
- Risk: standalone setup failures (Python/Tk mismatch, missing runtime pieces).
- Mitigation: startup preflight checks + explicit prerequisites and troubleshooting guidance in README.
- Verification: fresh-machine install tests on Windows and Linux.

8. **Velocity lifecycle connection churn**
- Risk: false-positive errors and unstable behavior during expected connect/disconnect cycles.
- Mitigation: treat lifecycle churn as expected state transitions, not exceptional paths.
- Verification: scripted testConnection/sampleMessages/feed-run loop test.

9. **Header-on-connect race conditions**
- Risk: transient disconnects during header send can surface as noisy failures.
- Mitigation: idempotent per-connection header send with graceful handling for disconnect-before-write.
- Verification: repeated connect/disconnect fuzzing with header mode enabled.

### What Users Will Still Hate

1. **Initial setup friction**
- Pain: source-only mode still requires a working Python + Tk environment.
- Mitigation: provide exact install commands and preflight diagnostics.

2. **Functional-but-minimal tkinter UX**
- Pain: dense tables and controls can feel dated and less discoverable.
- Mitigation: use clear defaults, sensible grouping, keyboard shortcuts, and consistent labels.

3. **Difficulty validating sent output quickly**
- Pain: users want fast confidence about what was actually emitted after timestamp rewrite.
- Mitigation: show last-sent payload summary and add copy/export affordances in status/log panels.

4. **Manual JSON editing errors**
- Pain: malformed config files are easy to create.
- Mitigation: schema-aware validation messages that identify exact field and failure reason.

---

## 8. Resolved Open Questions

All design questions have been resolved. See Section 2 for the complete decision log including RQ1–RQ21.

---

## 9. Proposed Milestones (Revised)

### MVP (Minimum Viable Product)

| Phase | Scope | Notes |
|-------|-------|-------|
| **Phase 1: Foundation** | Project structure, config schema + schema versioning/migration, JSON config load/save, streaming file reader with validation, unit tests | No GUI, no networking yet. Unit test baseline established. |
| **Phase 2: Transport (sender)** | `transport/base.py` (shared socket lifecycle), `tcp_server_sender.py` (broadcast), `tcp_client_sender.py` (auto-reconnect), `udp_server_sender.py`, `udp_client_sender.py`, connection manager with backpressure/slow client detection. Existing `tcp_server.py` / `tcp_client.py` / `udp_server.py` / `udp_client.py` modules are renamed to their `_sender` variants and their shared primitives extracted into `base.py`. | Must pass integration matrix scenarios `TM-INT-01`, `TM-INT-02`, `TM-INT-03`. Manual netcat/telnet is optional smoke only. |
| **Phase 2b: Transport (receiver) + Receiver engine** | `tcp_server_receiver.py`, `tcp_client_receiver.py`, `udp_server_receiver.py`, `udp_client_receiver.py` built on the shared `base.py`. Receiver engine (`engine/receiver.py` + `engine/framer.py` + `engine/sink_writer.py`), delimited + JSONL sink formats with rotation, runtime sink reconfiguration, per-peer TCP read-pause backpressure, UDP drop-and-count. | Must pass `TM-INT-04` and `TM-SOAK-03`. Sender ⇄ Receiver role toggle wired end-to-end through controller. |
| **Phase 3: Scheduler** | Rate control (features/s), step mode, jump-to-line, auto mode, loop mode, pause/resume, timestamp rewriting (ISO 8601, epoch millis, epoch seconds) | Must pass soak matrix scenarios `TM-SOAK-01`, `TM-SOAK-02`. |
| **Phase 4: GUI** | Main window, **role toggle (Sender/Receiver)**, config panel, file browser + preview (sender), sink file panel (receiver), transport controls (start/stop/pause/step/jump), runtime file/rate reconfiguration without restart, status panel (connections, rate, progress, blocking, receive stats, sink status), on-demand log panel (load/refresh), config save/load | Full GUI wired to engine. This is the MVP delivery. |

### Post-MVP

| Phase | Scope |
|-------|-------|
| **Phase 5: Enhanced Timing** | Original-rate replay mode (send at timestamp deltas), auto-detect timestamp format |
| **Phase 6: Line Control** | Start/end line selection, first N lines |
| **Phase 7: TLS/SSL** | Optional TLS for TCP server and client, certificate configuration in GUI |
| **Phase 8: Log Viewer** | Dedicated log viewer UI component with filtering, search, and export |
| **Phase 9: Packaging** | PyInstaller/cx_Freeze single-binary builds, Docker image, pip package |

---

*This document should be treated as a living artifact. Update it as requirements evolve and implementation insights are validated.*
