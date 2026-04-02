# TCP Server Simulator — Design & Requirements Document

> **Status:** DRAFT — Open questions resolved, ready for implementation planning  
> **Last Updated:** 2026-04-02  
> **Target Platforms:** Windows, Linux  
> **Language:** Python 3.10+  
> **Distribution:** Source only (for now)  
> **Interface:** GUI (with underlying engine decoupled for future CLI use)

---

## 1. Overview

A cross-platform TCP simulator for testing ArcGIS Velocity. The tool reads delimited text files (primarily CSV) and transmits their contents line-by-line over TCP at a configurable rate. It operates in two modes:

- **Server Mode:** Listens on a configured port, accepts inbound connections, and pushes data to connected clients.
- **Client Mode:** Connects outbound to a specified host:port and pushes data to the remote server.

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

**Velocity TCP Client Output (secondary use case):**
Velocity RATs can also output data to an external TCP server. In this scenario, our simulator would be in **Server mode listening** — but the current scope only covers *sending* data. Receiving data from Velocity is out of scope for MVP.

**Velocity TCP Server Feed (reverse direction):**
Our simulator in **Client mode** connects to Velocity's TCP Server feed to push data inward. Less commonly tested but supported.

### 1.2 Data Format Considerations

**The simulator is format-agnostic.** It sends raw text lines terminated by a configurable record separator. The downstream consumer (Velocity) interprets the format.

Velocity supports these formats for TCP feeds:
- Delimited (comma, pipe, semicolon, tab — our primary focus)
- JSON
- GeoJSON
- EsriJSON
- XML

Because our simulator reads a file and sends it line-by-line, it can serve any of these formats as long as the file contains properly formatted data with one record per line. The simulator does not parse or validate the data format itself — only column count consistency for delimited files.

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
| Q15 | Line subsetting | **Post-MVP** — MVP sends all lines with looping. Later: start/end line, first N. No random sampling. | No |
| Q16 | Log format | **JSON structured**. Post-MVP: log viewer UI component | Yes (JSON), No (viewer) |
| Q17 | Config files | **Yes, JSON format** | Yes |
| Q18 | GeoEvent compatibility | **No** — clean-slate design | N/A |
| Q19 | Primary users | **Product Engineers** testing ArcGIS Velocity for Enterprise | N/A |
| Q20 | Multiple files | **No** — single file per instance. Run separate copies for separate files. | Yes |

---

## 3. Functional Requirements

### 3.1 Operating Modes

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The application shall support **Server mode**: bind to a port, accept TCP connections, and broadcast data to all connected clients. | MVP |
| FR-02 | The application shall support **Client mode**: connect to a remote host:port and transmit data. | MVP |
| FR-03 | The user shall be able to switch between Server and Client modes via the GUI without restarting the application. | MVP |
| FR-04 | The application shall support **TCP** and **UDP** protocols, selectable in the GUI. | MVP |
| FR-04a | In server mode, the application shall gracefully handle clients that **connect and disconnect repeatedly** (e.g., Velocity's testConnection → sampleMessages → feed run lifecycle). Disconnections shall not interrupt transmission to other clients or cause errors. | MVP |

### 3.2 File Loading & Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-05 | The application shall allow the user to select and load a delimited text file (CSV, TSV, or custom delimiter) via a file browser dialog. | MVP |
| FR-06 | The user shall be able to configure the field delimiter character in the GUI. | MVP |
| FR-07 | The application shall support a configurable header row toggle. When enabled, the first line is treated as field names (used for field selection dropdowns). | MVP |
| FR-08 | The user shall be able to toggle whether the header row is sent to clients. When enabled in server mode, the header shall be sent as the **first message to each newly connected client**. | MVP |
| FR-09 | The application shall display a preview of the loaded file (first N rows, field count, total line count) in the GUI. | MVP |
| FR-10 | The application shall handle files with inconsistent line endings (CRLF, LF). | MVP |
| FR-11 | The application shall support UTF-8 encoded files. | MVP |
| FR-12 | The application shall validate column count consistency on load. Lines with inconsistent column counts shall be **discarded** and logged. | MVP |

### 3.3 Data Transmission

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-13 | Each line of the loaded file shall be sent as a discrete message, terminated by a configurable line ending (default: `\n`). | MVP |
| FR-14 | The user shall be able to configure the send rate in **features per second** (1 feature = 1 line). | MVP |
| FR-15 | The GUI shall display both **features/s** and **KB/s** in real time during transmission. | MVP |
| FR-16 | The application shall support **automatic mode**: continuously send lines at the configured rate. | MVP |
| FR-17 | The application shall support **step mode**: send one line per user click (manual advance). | MVP |
| FR-18 | The application shall support **looping**: when EOF is reached, restart from the first data line. Looping is on by default in automatic mode. | MVP |
| FR-19 | The application shall allow the user to **pause and resume** transmission without dropping connections. | MVP |
| FR-20 | The GUI shall display the current line number, total lines, and a progress indicator during transmission. | MVP |
| FR-21 | Post-MVP: Support **original-rate mode** — send lines at the rate implied by the timestamp deltas in the original data. | Post-MVP |
| FR-22 | Post-MVP: Support sending a **subset of lines** (start/end line, first N lines). | Post-MVP |

### 3.4 Timestamp Field Handling

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-23 | The user shall be able to designate a field (by name from header, or by index) as the **timestamp field** via a GUI dropdown. | MVP |
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
| FR-33 | The application shall support configurable **connection timeout** and **send timeout** values. | MVP |
| FR-34 | Post-MVP: Optional **TLS/SSL** support with certificate configuration. | Post-MVP |

### 3.6 Logging & Reporting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-35 | The application shall log all connection events (connect, disconnect, reconnect, slow client disconnect) in **JSON structured format**. | MVP |
| FR-36 | The application shall log transmission statistics: features sent, bytes sent, elapsed time, current rate (feat/s and KB/s). | MVP |
| FR-37 | The application shall write JSON logs to a configurable log file. | MVP |
| FR-38 | The GUI shall display a live scrolling log view showing recent JSON log entries. | MVP |
| FR-39 | Log verbosity shall be configurable (DEBUG, INFO, WARN, ERROR). | MVP |
| FR-40 | Post-MVP: Dedicated log viewer UI component with filtering and search. | Post-MVP |

### 3.7 Configuration Management

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-41 | The application shall support saving the current configuration to a **JSON file**. | MVP |
| FR-42 | The application shall support loading a previously saved JSON configuration file, populating all GUI fields. | MVP |
| FR-43 | The application shall provide sensible defaults for all configuration values. | MVP |

---

## 4. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | The application shall run on Windows 10+ and common Linux distributions (Ubuntu 20.04+, RHEL 8+) with Python 3.10+ installed. | MVP |
| NFR-02 | The application shall **stream** files line-by-line. No file size limit; memory usage shall remain bounded regardless of file size. | MVP |
| NFR-03 | The application shall support at least **50 simultaneous client connections** in server mode. | MVP |
| NFR-04 | The application shall provide a **GUI** as its primary interface. The engine shall be decoupled to allow future CLI use. | MVP |
| NFR-05 | The application shall be distributed as **source only** (clone + `pip install -r requirements.txt` + `python -m tcp_sim`). | MVP |
| NFR-06 | The application shall shut down gracefully on window close or SIGINT/SIGTERM, closing all connections cleanly. | MVP |
| NFR-07 | The application shall not crash or hang when a client disconnects unexpectedly. | MVP |
| NFR-08 | The GUI shall remain responsive during file loading, transmission, and high connection counts. All I/O shall be async. | MVP |

---

## 5. Architecture & Design

### 5.1 Technology Stack

**Decided:** Python 3.10+ with `asyncio` for async TCP/UDP handling.

**GUI Framework (to be decided — see remaining open questions):**
- **Option A: PySide6 / PyQt6** — Full desktop GUI. Mature, powerful, cross-platform. Heavy dependency (~150 MB). Best for complex interactive UIs with real-time updates.
- **Option B: tkinter + ttkbootstrap** — Lightweight, ships with Python. Limited widget set but sufficient for this tool. Zero additional dependencies.
- **Option C: NiceGUI / Gradio** — Web-based UI served locally. Modern look, easy layout. Requires browser. Good for dashboards and real-time stats display.
- **Option D: Dear PyGui** — GPU-accelerated immediate-mode GUI. Fast real-time updates. Smaller community.

**Distribution:** Source-only. Users clone the repo and run with Python 3.10+. Dependencies managed via `requirements.txt` or `pyproject.toml`.

**Key Libraries (anticipated):**
- `asyncio` — TCP/UDP server and client
- `json` — Config files, structured logging
- `csv` — File parsing (with manual fallback for custom delimiters)
- `pathlib` — Cross-platform path handling
- `logging` — Structured JSON logging via custom formatter
- GUI framework TBD

**Alternative:** Go or Rust for true single-binary distribution and lower resource usage. Requires compilation per platform.

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
│  Log (JSON):                                [Clear] [Save]│
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
- **UDP Server mode:** Send datagrams to a configured multicast group or to all addresses that have previously sent a packet to the listen port.
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
- Not reset the line position when a client disconnects and reconnects
- Log connect/disconnect events at INFO level (not WARN/ERROR — these are expected)

#### Header Row Handling
- The first line of the CSV is assumed to be a header by default.
- The header is used for field name display in the GUI (e.g., timestamp field dropdown).
- The user can toggle whether the header is sent to clients as the first message.
- When "send header" is enabled, the header should be sent as the **first message to each new client connection**. This is critical for Velocity's sampleMessages phase — Velocity uses the first few messages to derive the data schema, and the header row helps it map field names correctly.
- If "no header" is configured, the first line is treated as data.

#### CSV Validation
On file load, check column count consistency. Lines with inconsistent column counts are **discarded** (not sent) and logged with a warning. The GUI file preview should flag invalid lines.

#### File Reading Strategy
Stream the file line-by-line using a buffered reader. Do not load the entire file into memory. For looping, seek back to the start of data (after header row, if any). Count total lines on initial load (single pass) for progress display.

#### Backpressure & Slow Clients
Monitor per-client TCP write buffer. If a client's buffer exceeds a threshold:
1. Log the blocking status (JSON structured log).
2. Show blocking indicator in the GUI.
3. If the client cannot drain within a configurable timeout, **disconnect** it.
4. Log the disconnection with client address and reason.
5. Show disconnected slow clients in the GUI status area.

Do **not** slow down the broadcast for other clients because one client is slow.

#### Client Mode: Auto-Reconnect
On disconnect, automatically attempt to reconnect with exponential backoff (e.g., 1s, 2s, 4s, 8s, max 30s). Display:
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

This preserves the relative timing between events while anchoring them to the current wall clock.

#### Rate Control
- Primary unit: **features per second** (1 feature = 1 CSV data line).
- The GUI displays both features/s and KB/s in real time.
- Post-MVP: **original-rate mode** — use timestamp deltas between consecutive rows to determine send timing.

### 5.4 Configuration

Configuration is saved/loaded as **JSON** files. The GUI provides a "Save Config" / "Load Config" button pair.

The config file stores all user-configurable settings:

```json
{
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
  "log_level": "INFO"
}
```

The GUI is the primary interface. All settings are configurable through the GUI. A future CLI mode could consume the same JSON config files.

### 5.5 Proposed Project Structure

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
│       │   └── simulator.py         # Orchestrates reader + scheduler + transport
│       ├── transport/
│       │   ├── __init__.py
│       │   ├── tcp_server.py        # asyncio TCP server, broadcast, backpressure
│       │   ├── tcp_client.py        # asyncio TCP client, auto-reconnect
│       │   ├── udp_server.py        # asyncio UDP sender
│       │   ├── udp_client.py        # asyncio UDP sender
│       │   └── connection_manager.py # Track clients, slow client detection
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
│           └── log_panel.py         # Live JSON log display
├── tests/
│   ├── test_file_reader.py
│   ├── test_scheduler.py
│   ├── test_timestamp.py
│   ├── test_tcp_server.py
│   ├── test_tcp_client.py
│   └── test_config.py
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

---

## 7. Risk Register & Cautions

### Implementation Risks

1. **GUI + asyncio threading.** This is where Python GUI apps go to die. The GUI event loop and the asyncio event loop are fundamentally different beasts. You need a clean threading model from day one or you'll get freezes, race conditions, and deadlocks. Plan the controller layer carefully.

2. **UDP "server" semantics are weird.** UDP is connectionless. Your "server mode" for UDP needs a clear definition of who receives the data. "Send to everyone who's ever sent us a packet" sounds simple until you realize you need to track stale addresses, handle NAT, and decide when to stop sending to a client that went away.

3. **Timestamp rewriting with custom formats.** Parsing epoch seconds as both integer and fractional means you need to distinguish `1712000000` from `1712000000.123`. Edge cases: negative timestamps, timestamps before epoch, timestamps in the year 2038+ as 32-bit integers. Define your parsing rules tightly.

4. **Streaming + looping + validation.** You're streaming the file (good), but you also need to count total lines on load (for progress display), skip invalid lines (for validation), and seek back to data start (for looping). Make sure your file reader handles all three concerns without loading the file into memory.

5. **"Source only" distribution.** Your users are Product Engineers. If they have to debug Python version conflicts and missing dependencies, they will abandon this tool. At minimum, provide a `requirements.txt` with pinned versions and clear setup instructions. Consider a `Makefile` or `justfile` for one-command setup.

6. **Velocity's connect/disconnect churn.** Per the reference docs, Velocity disconnects and reconnects multiple times during feed configuration. If your server logs these as errors or — worse — crashes on sudden disconnects, your PEs will think the tool is broken during perfectly normal operation. The connection manager must treat rapid connect/disconnect cycles as business as usual. Write buffer cleanup on disconnect must be bulletproof.

7. **Header-on-connect timing.** If "send header" is enabled and you send the header to each new client on connect, you need to handle the race condition where a client connects between broadcast ticks. If the header send fails because the client already disconnected (Velocity's testConnection phase), you must not propagate that error.

### What Users Will Still Hate

1. **Having to install Python.** Even "source only" requires a working Python 3.10+ environment. Not every Windows machine has one. Include a "Prerequisites" section in the README with exact install steps.

2. **GUI framework choice matters.** tkinter looks like a tool from 1997. PySide6 looks professional but adds ~150 MB of dependencies. NiceGUI opens a browser tab, which some users find weird. Pick wrong and you'll hear about it.

3. **No way to see what was *actually sent*.** The preview shows file contents, but users will want to see the exact bytes that went over the wire — especially when timestamp rewriting is active. Consider a "last sent line" display in the status panel.

4. **Config files are JSON.** Your users will forget trailing commas, mistype a boolean, and get a confusing parse error. Provide very clear error messages on config load failure, ideally pointing to the exact line/field that's wrong.

---

## 8. Remaining Open Questions

Most design questions have been resolved (see Section 2). The following still need decisions before or during implementation:

### GUI Framework

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| RQ1 | **Which Python GUI framework?** | PySide6/PyQt6, tkinter+ttkbootstrap, NiceGUI (web-based), Dear PyGui | PySide6 for a serious desktop app. tkinter if you want zero deps. NiceGUI if your users are comfortable with a browser opening. |
| RQ2 | **Should the GUI support theming / dark mode?** | Yes, No, System-follows | Most engineers prefer dark mode. PySide6 and ttkbootstrap support it natively. |

### Network Details

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| RQ3 | **UDP server mode: how to discover recipients?** | Send to multicast group, Send to all IPs that have sent us a packet, Configure target list manually | Multicast is cleanest but requires network configuration. "Reply to senders" is most practical. |
| RQ4 | **What is the slow-client disconnect timeout?** | Fixed (e.g., 5s), Configurable, Scale with send rate | Configurable with a sensible default (5-10 seconds). |
| RQ5 | **What is the max reconnect backoff interval (client mode)?** | Fixed at 30s, Configurable, Unlimited | Configurable with a default of 30 seconds. |

### Data

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| RQ6 | **How many preview rows to show in the GUI?** | 5, 10, 20, Configurable | 10 rows is a good default. |
| RQ7 | **Should discarded (invalid) lines be shown in the preview?** | Yes (highlighted), No (filtered out), Summary count only | Show in preview highlighted red, with a count of total discarded. |

### Operational

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| RQ8 | **Should the app remember the last-used config on startup?** | Yes (auto-load last config), No (always start fresh), Ask user | Auto-load last config. Engineers iterate on the same test repeatedly. |
| RQ9 | **Log rotation / max log file size?** | No rotation, Rotate at 10MB, Configurable | Configurable with a sensible default. Without it, overnight tests will produce enormous log files. |

---

## 9. Proposed Milestones (Revised)

### MVP (Minimum Viable Product)

| Phase | Scope | Notes |
|-------|-------|-------|
| **Phase 1: Foundation** | Project structure, config schema, JSON config load/save, streaming file reader with validation, unit tests | No GUI, no networking yet. Just the engine core. |
| **Phase 2: Transport** | TCP server (broadcast), TCP client (with auto-reconnect), UDP server, UDP client, connection manager with backpressure/slow client detection | Test with netcat/telnet. No GUI yet. |
| **Phase 3: Scheduler** | Rate control (features/s), step mode, auto mode, loop mode, pause/resume, timestamp rewriting (ISO 8601, epoch millis, epoch seconds) | Integrates engine + transport. Testable via scripts. |
| **Phase 4: GUI** | Main window, config panel, file browser + preview, transport controls (start/stop/pause/step), status panel (connections, rate, progress, blocking), live log panel, config save/load | Full GUI wired to engine. This is the MVP delivery. |

### Post-MVP

| Phase | Scope |
|-------|-------|
| **Phase 5: Enhanced Timing** | Original-rate replay mode (send at timestamp deltas), auto-detect timestamp format |
| **Phase 6: Line Control** | Start/end line selection, first N lines, jump-to-line in step mode |
| **Phase 7: TLS/SSL** | Optional TLS for TCP server and client, certificate configuration in GUI |
| **Phase 8: Log Viewer** | Dedicated log viewer UI component with filtering, search, and export |
| **Phase 9: Packaging** | PyInstaller/cx_Freeze single-binary builds, Docker image, pip package |

---

*This document should be treated as a living artifact. Update it as open questions are resolved.*
