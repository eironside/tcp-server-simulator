# TCP Server Simulator — Design & Requirements Document

> **Status:** DRAFT — Pending answers to open questions before implementation  
> **Last Updated:** 2026-04-02  
> **Target Platforms:** Windows, Linux

---

## 1. Overview

A cross-platform TCP simulator for testing ArcGIS Velocity. The tool reads delimited text files (primarily CSV) and transmits their contents line-by-line over TCP at a configurable rate. It operates in two modes:

- **Server Mode:** Listens on a configured port, accepts inbound connections, and pushes data to connected clients.
- **Client Mode:** Connects outbound to a specified host:port and pushes data to the remote server.

The tool is a spiritual successor to the GeoEvent TCP Simulator (Java), rebuilt for modern use.

---

## 2. Functional Requirements

### 2.1 Operating Modes

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-01 | The application shall support **Server mode**: bind to a port, accept TCP connections, and transmit data to all connected clients. | Must |
| FR-02 | The application shall support **Client mode**: connect to a remote host:port and transmit data. | Must |
| FR-03 | The user shall be able to switch between Server and Client modes without restarting the application. | Should |

### 2.2 File Loading & Parsing

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-04 | The application shall allow the user to select and load a delimited text file (CSV, TSV, or custom delimiter). | Must |
| FR-05 | The user shall be able to configure the field delimiter character. | Must |
| FR-06 | The application shall support a configurable header row (skip first N lines, or use first line as field names). | Must |
| FR-07 | The application shall display a preview of the loaded file (first N rows, field count, total line count). | Should |
| FR-08 | The application shall handle files with inconsistent line endings (CRLF, LF). | Must |
| FR-09 | The application shall support UTF-8 encoded files. Support for other encodings is optional. | Must |

### 2.3 Data Transmission

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-10 | Each line of the loaded file shall be sent as a discrete TCP message, terminated by a configurable line ending (default: `\n`). | Must |
| FR-11 | The user shall be able to configure the send rate (e.g., lines per second, or milliseconds between lines). | Must |
| FR-12 | The application shall support **automatic mode**: continuously send lines at the configured rate. | Must |
| FR-13 | The application shall support **step mode**: send one line per user action (manual advance). | Must |
| FR-14 | The application shall support **looping**: when the end of file is reached, optionally restart from the beginning. | Must |
| FR-15 | The application shall allow the user to **pause and resume** transmission without dropping connections. | Should |
| FR-16 | The application shall display the current line number and total lines during transmission. | Should |

### 2.4 Timestamp Field Handling

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-17 | The user shall be able to designate a field (by index or name) as the **timestamp field**. | Must |
| FR-18 | The user shall be able to configure the timestamp format (e.g., ISO 8601, epoch millis, custom strftime pattern). | Must |
| FR-19 | When a timestamp field is designated, the application shall replace the original timestamp with a **current-time-based value** at send time, preserving the relative offset between consecutive rows. | Must |
| FR-20 | The user shall be able to disable timestamp replacement (send raw file data). | Must |

### 2.5 Network Configuration

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-21 | The user shall be able to configure the **TCP port** (server: listen port; client: destination port). | Must |
| FR-22 | In client mode, the user shall be able to configure the **destination host/IP**. | Must |
| FR-23 | In server mode, the application shall be able to configure the **bind address** (default: `0.0.0.0`). | Should |
| FR-24 | The application shall support configurable **connection timeout** and **send timeout** values. | Should |

### 2.6 Logging & Reporting

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-25 | The application shall log all connection events (connect, disconnect, errors). | Must |
| FR-26 | The application shall log transmission statistics (lines sent, bytes sent, elapsed time, current rate). | Must |
| FR-27 | The application shall write logs to both the console and a log file. | Should |
| FR-28 | Log verbosity shall be configurable (e.g., DEBUG, INFO, WARN, ERROR). | Should |

---

## 3. Non-Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| NFR-01 | The application shall run on Windows 10+ and common Linux distributions (Ubuntu 20.04+, RHEL 8+) without requiring additional runtime installation beyond the chosen platform. | Must |
| NFR-02 | The application shall handle files up to at least **1 GB** without loading the entire file into memory. | Should |
| NFR-03 | The application shall support at least **50 simultaneous client connections** in server mode. | Should |
| NFR-04 | The application shall provide a **CLI interface** at minimum. A GUI/TUI is optional. | Must |
| NFR-05 | The application shall be distributable as a single binary or self-contained package (no Java dependency). | Should |
| NFR-06 | The application shall shut down gracefully on SIGINT/SIGTERM, closing all connections cleanly. | Must |
| NFR-07 | The application shall not crash or hang when a client disconnects unexpectedly. | Must |

---

## 4. Architecture & Design

### 4.1 Technology Stack

**Recommended:** Python 3.10+ with `asyncio` for async TCP handling.

**Rationale:**
- Cross-platform without compilation
- `asyncio` provides efficient concurrent connection handling
- Easy CSV/file parsing with stdlib
- Simple distribution via `pip` or `pyinstaller` for single-binary packaging
- Low barrier to entry for Esri teams to contribute

**Alternative:** Go or Rust for true single-binary distribution and lower resource usage. Requires compilation per platform.

### 4.2 High-Level Components

```
┌─────────────────────────────────────────────────┐
│                   CLI / TUI                      │
│          (argument parsing, user input)          │
├─────────────────────────────────────────────────┤
│               Simulator Engine                   │
│  ┌───────────┐  ┌────────────┐  ┌────────────┐ │
│  │ File       │  │ Send       │  │ Timestamp  │ │
│  │ Reader     │  │ Scheduler  │  │ Rewriter   │ │
│  └───────────┘  └────────────┘  └────────────┘ │
├─────────────────────────────────────────────────┤
│             Transport Layer                      │
│  ┌───────────────────┐  ┌────────────────────┐  │
│  │  Server Transport  │  │  Client Transport  │  │
│  │  (listen/accept)   │  │  (connect/send)    │  │
│  └───────────────────┘  └────────────────────┘  │
├─────────────────────────────────────────────────┤
│          Connection Manager                      │
│    (track clients, handle disconnects,           │
│     broadcast vs. independent streams)           │
├─────────────────────────────────────────────────┤
│              Logging / Stats                     │
└─────────────────────────────────────────────────┘
```

### 4.3 Key Design Decisions

#### Message Framing
Each CSV line is sent as a newline-terminated string. The receiver is expected to parse on newline boundaries. The line terminator sent over the wire should be configurable (`\n`, `\r\n`, or none).

#### Server Mode: Broadcast vs. Independent Streams
- **Broadcast (recommended default):** All connected clients receive the same line at the same time. A client that connects mid-stream joins at whatever line is current.
- **Independent streams (optional):** Each client gets its own stream starting from line 1. More complex, higher memory usage.

#### File Reading Strategy
Stream the file line-by-line using a buffered reader. Do not load the entire file into memory. For looping, seek back to the start of data (after header row, if any).

#### Timestamp Rewriting
1. Parse the designated timestamp field from the **first data row** as T₀.
2. For each subsequent row, calculate `offset = row_timestamp - T₀`.
3. At send time, compute `new_timestamp = now() + offset`.
4. Replace the field value in the outgoing line with the new timestamp formatted per the configured pattern.

This preserves the relative timing between events while anchoring them to the current wall clock.

### 4.4 Configuration

The application should accept configuration via:
1. **Command-line arguments** (highest priority)
2. **Configuration file** (YAML or JSON, lower priority)
3. **Sensible defaults** for everything

Example CLI:
```bash
# Server mode
tcp-sim server --port 5565 --file data.csv --rate 10 --loop

# Client mode
tcp-sim client --host 192.168.1.100 --port 5565 --file data.csv --rate 10

# Step mode
tcp-sim server --port 5565 --file data.csv --step

# With timestamp rewriting
tcp-sim server --port 5565 --file data.csv --rate 10 --timestamp-field 3 --timestamp-format "%Y-%m-%dT%H:%M:%S"
```

---

## 5. What the Original Spec is Missing

| Gap | Impact | Recommendation |
|-----|--------|----------------|
| **No technology stack specified** | Can't start implementation. Python, Go, Rust, Node, C# are all viable with different tradeoffs. | Decide before writing a line of code. |
| **No message framing defined** | Receivers won't know where one message ends and another begins. Silent data corruption. | Define line terminator behavior explicitly. |
| **No encoding specification** | Non-ASCII characters (location names, sensor IDs) will break silently. | Default to UTF-8, document it. |
| **No server broadcast semantics** | Do all clients see the same stream? Do late joiners start from line 1? Completely undefined. | Define broadcast vs. independent stream behavior. |
| **No header row handling** | First line of most CSVs is column names. Sending `"lat,lon,timestamp,id"` as data will confuse consumers. | Support skip-header and send-header-to-each-client options. |
| **No reconnection logic (client mode)** | One network blip and your 8-hour test run is dead. | Implement configurable auto-reconnect with backoff. |
| **No pause/resume** | Users can't inspect mid-stream without killing the process. | Add pause/resume support. |
| **No progress indication** | Users staring at a blank terminal wondering if it's working or frozen. | Show line count, rate, and connection status. |
| **No max connection limit (server mode)** | A misbehaving test could open 10,000 connections and OOM the simulator. | Set a configurable max. |
| **No TLS/SSL support** | ArcGIS Velocity may require encrypted connections in production-like testing. | At minimum, plan for optional TLS. |
| **No send-header option** | Some consumers need the CSV header as the first message on each connection. Others don't. | Make it configurable. |
| **No configuration file support** | Users will be typing 15-flag CLI commands and hating life. | Support a config file. |
| **"Detailed logging and reporting" is undefined** | Could mean anything from `print("sent line")` to Prometheus metrics. | Specify exactly what metrics and what format. |
| **Rate unit is ambiguous** | "Configurable rate" — lines/sec? ms/line? Variable rate matching original timestamps? | Define the unit and support multiple modes. |

---

## 6. What You'll Regret

1. **Not supporting config files from day one.** You'll hardcode CLI args, then realize every test scenario needs a different 12-flag command. You'll wish you had `tcp-sim --config velocity-test.yaml` from the start.

2. **Not thinking about the header row.** Every CSV has one. Every consumer handles it differently. You'll get bug reports day one.

3. **Not implementing reconnection in client mode.** Networks are unreliable. Your users will run overnight tests. They will lose hours of data because a switch hiccupped at 3 AM.

4. **Not streaming the file.** Someone will try to load a 2 GB fleet tracking dataset and your simulator will eat all their RAM and crash. They won't file a bug; they'll just stop using your tool.

5. **Not defining what "rate" means clearly.** `--rate 10` could mean 10 lines/sec, 10 ms between lines, or 10 lines/min. Pick one, document it, support alternatives.

6. **Skipping graceful shutdown.** Ctrl+C during a test will leave TCP connections in TIME_WAIT, and the port will be unavailable for 30-60 seconds. Your users will think the tool is broken.

7. **Not considering what happens when send rate exceeds network capacity.** Backpressure is real. TCP buffers fill up. Your send loop blocks or drops data. Neither is good if you don't handle it intentionally.

---

## 7. What Your Users Will Hate

1. **No visual feedback.** A tool that accepts input and produces silence is indistinguishable from a tool that's frozen. Show a progress bar, line counter, connection count, *something*.

2. **No way to jump to a specific line.** Step mode is great until you need to test line 4,572. Nobody wants to press Enter 4,571 times.

3. **No file validation before sending.** Loading a binary file or a CSV with ragged columns and getting garbage output with no warning.

4. **No way to preview what will be sent.** Users want to see the first few lines (with timestamp rewriting applied) before committing to a full run.

5. **Cryptic error messages.** "Connection refused" with no mention of which host:port, or "File error" with no path. Invest in error messages or invest in support tickets.

6. **Having to restart to change the file or rate.** If I'm iterating on test data, I don't want to kill the process, re-type the command, and wait for clients to reconnect every time I tweak the CSV.

7. **No send count / line limit option.** "Send the first 100 lines and stop" is a basic testing workflow. Without it, users will Ctrl+C and hope they timed it right.

8. **Platform-specific path handling.** Backslashes on Windows, forward slashes on Linux. If you don't normalize paths, one platform's users will always be filing bugs.

---

## 8. Open Questions (Must Answer Before Implementation)

### Technology & Distribution

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q1 | **What language/runtime should this be built in?** | Python 3.10+, Go, Rust, C# (.NET), Node.js | Determines build system, distribution, performance ceiling, and contributor pool. |
| Q2 | **How will the tool be distributed?** | pip package, standalone binary (PyInstaller/GraalVM), Docker image, source-only | Affects packaging, CI/CD, and what users need pre-installed. |
| Q3 | **Is a GUI required, or is CLI-only acceptable?** | CLI only, TUI (terminal UI), Web UI, Desktop GUI | Massive scope difference. A TUI with `textual` or `rich` is a reasonable middle ground. |

### Network Behavior

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q4 | **Server mode: broadcast or independent streams?** | Broadcast (all clients see same line), Independent (each client starts from line 1), Configurable | Defines core server architecture. |
| Q5 | **Should the header row be sent to clients?** | Always, Never, Configurable (per-connection or globally) | Affects how consumers parse incoming data. |
| Q6 | **Is TLS/SSL support required?** | Not now, Optional (self-signed), Required (with cert config) | Adds significant complexity if required. |
| Q7 | **Client mode: should it auto-reconnect on disconnect?** | Yes with configurable backoff, No (exit on disconnect), Configurable | Critical for long-running tests. |
| Q8 | **What should happen when send buffer is full (backpressure)?** | Block (slow down), Drop lines, Buffer in memory with limit, Disconnect slow client | Determines behavior under load. |
| Q9 | **Should the simulator support UDP in addition to TCP?** | TCP only, TCP + UDP | Some Velocity feeds may use UDP. |

### Data Handling

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q10 | **What is the default unit for send rate?** | Lines per second, Milliseconds between lines, Match original timestamps | Determines core timing behavior. |
| Q11 | **Should "match original timestamps" be a rate mode?** | Yes (replay at real speed), No (fixed rate only) | If the CSV has timestamps 5 seconds apart, send lines 5 seconds apart. Powerful but complex. |
| Q12 | **What timestamp formats must be supported?** | ISO 8601 only, Epoch millis, Custom strftime, Auto-detect | Auto-detect is fragile. Explicit is better. |
| Q13 | **Should the tool validate CSV structure before sending?** | Yes (check column count consistency), No (send raw lines), Warn but continue | Prevents garbage-in, garbage-out. |
| Q14 | **Maximum supported file size?** | No limit (streaming), Configurable memory cap | Determines file reading strategy. |
| Q15 | **Should the tool support sending a subset of lines?** | Start line / end line, First N lines, Random sampling | Common testing workflow. |

### Operational

| # | Question | Options | Impact |
|---|----------|---------|--------|
| Q16 | **What log format is required?** | Plain text, JSON structured, Both | JSON is better for automated analysis. |
| Q17 | **Should configuration be saveable/loadable from a file?** | Yes (YAML/JSON/TOML), No (CLI args only) | Major usability factor for repeated test scenarios. |
| Q18 | **Is there an existing GeoEvent TCP Simulator command set we need to be compatible with?** | Yes (document it), No (clean-slate design) | If users are migrating, compatibility reduces friction. |
| Q19 | **Who are the primary users?** | QA engineers, developers, field consultants, automated CI pipelines | Determines UX priorities (interactive vs. scriptable). |
| Q20 | **Should the tool support multiple simultaneous file sources?** | Single file only, Multiple files to different ports | Scope creep risk, but real-world use case. |

---

## 9. Proposed Milestones

| Phase | Scope | Dependencies |
|-------|-------|-------------|
| **Phase 1: Core** | Server mode, client mode, file loading, fixed-rate sending, basic CLI, basic logging | Q1-Q4 answered |
| **Phase 2: Usability** | Config files, step mode, pause/resume, progress display, loop mode, send-header option | Phase 1 complete |
| **Phase 3: Timestamp** | Timestamp field designation, format parsing, real-time rewriting, original-rate replay | Phase 1 complete, Q10-Q12 answered |
| **Phase 4: Resilience** | Auto-reconnect, backpressure handling, graceful shutdown, large file streaming | Phase 1 complete |
| **Phase 5: Polish** | File validation, line subset sending, jump-to-line in step mode, TLS support, packaging | Phases 1-4 complete |

---

*This document should be treated as a living artifact. Update it as open questions are resolved.*
