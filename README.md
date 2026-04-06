# tcp-server-simulator

TCP/UDP simulator for ArcGIS Velocity validation.

## What This Project Does

- Runs in server or client mode
- Supports TCP and UDP transports
- Streams delimited files without full in-memory loading
- Supports step/auto/loop scheduling primitives
- Provides a tkinter GUI with transport, file, status, and on-demand log panels
- Enforces automated unit, integration, and soak gates

## Quick Start (venv-first)

### Windows (PowerShell)
Run the run.ps1 script in Powershell.

Contents of that script:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py
python -m tcp_sim
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py
python -m tcp_sim
```

## Preflight

Run before launch to validate prerequisites:

```bash
python scripts/preflight.py
```

Checks include:

- Python version (`>=3.10`)
- Active virtual environment
- tkinter/Tk runtime availability

Use headless validation only:

```bash
python -m tcp_sim --preflight-only
python -m tcp_sim --headless
```

## Test Gates

```bash
pytest -m unit -q
pytest -m integration -q
pytest -m soak -q
```

Threshold-based matrix checks are enforced in tests via environment variables (for CI profiles and local stress runs). Example:

```bash
TM_INT_01_CONNECTION_ROUNDS=120 pytest -m integration -q
TM_SOAK_01_DURATION_SECONDS=120 TM_SOAK_02_UNIQUE_SENDERS=2000 pytest -m soak -q
```

## Runbook

### Server Mode (Velocity TCP Client Feed)

1. Start app: `python -m tcp_sim`
2. Set mode `server`, protocol `tcp`, bind host/port.
3. Load data file and preview rows.
4. For Velocity delimited sampling, enable `Velocity Delimited Sampling Compatibility`.
5. Keep `Header Row` on if your file contains a header, but let the preset disable `Send Header` during sampling.
6. Start transport.
7. Confirm status panel updates for connections and progress.

### Client Mode (Push Into Remote TCP Server)

1. Set mode `client`, protocol `tcp`, destination host/port.
2. Start transport.
3. Verify reconnect events on upstream outage/recovery.

### UDP Reply-To-Senders Mode

1. Set protocol `udp` with server mode.
2. Send initial datagrams from peers to seed recipient cache.
3. Broadcast payloads and validate recipient churn behavior.

## Troubleshooting

### Preflight fails with virtual environment error

- Cause: shell is not using the project venv.
- Fix: activate `.venv` and rerun `python scripts/preflight.py`.

### tkinter import/runtime error on Linux

- Cause: Tk bindings missing from Python installation.
- Fix: install distro package (commonly `python3-tk`) and rerun preflight.

### No TCP server clients receiving data

- Cause: wrong bind host/port, local firewall, or no subscriber connected.
- Fix: verify host/port, open firewall rules, and check client count in status panel.

### Client mode reconnects repeatedly

- Cause: destination unavailable or connection refused.
- Fix: verify remote endpoint is up and routing/firewall permit access.

### Velocity shows raw samples but empty derived samples for delimited TCP

- Cause: sampling can fail when each sampled record is parsed with header handling enabled and a header line is transmitted.
- Fix: turn on `Velocity Delimited Sampling Compatibility` so the simulator suppresses the transmitted header and preserves LF delimiters.

### Soak tests fail on memory thresholds

- Cause: environment pressure or regression in stream lifecycle.
- Fix: rerun with diagnostics, inspect new commits affecting file reader, transport queues, or UDP recipient cache.

## Exploratory Socket Checks (Non-Gating)

Manual socket tools are helpful for quick smoke checks but do not replace automated gates.

Examples:

```powershell
# PowerShell TCP listener smoke
Test-NetConnection -ComputerName 127.0.0.1 -Port 5565
```

```bash
# Linux TCP listener smoke
nc -vz 127.0.0.1 5565
```

## CI Profiles

- Setup validation runs on Windows and Linux (`scripts/preflight.py`).
- Unit and integration suites run on every PR/push.
- Soak baseline runs in CI with explicit threshold env values.
- Full soak profile is enabled for `release/*` branches.

## Packaging

### pip package artifacts (wheel + sdist)

```bash
pip install -e .[packaging]
python scripts/package_pip.py
```

### PyInstaller binary

```bash
pip install -e .[packaging]
python scripts/package_pyinstaller.py
```

### cx_Freeze binary

```bash
pip install -e .[packaging]
python scripts/package_cxfreeze.py
```

### Docker image

```bash
docker build -t tcp-server-simulator:latest .
docker run --rm tcp-server-simulator:latest
```

## Known MVP Constraints

- GUI is functional-first (tkinter stdlib), not style-optimized.
- Advanced replay-by-original-timestamp modes are post-MVP.
- Manual socket checks are informational and non-gating.
