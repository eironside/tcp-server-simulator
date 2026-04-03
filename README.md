# tcp-server-simulator

TCP and UDP simulator for ArcGIS Velocity testing.

## Current Status

Phase 0 bootstrap is in place:

- Source layout scaffolded under `src/tcp_sim`
- Editable install support via `pyproject.toml`
- Standalone environment readiness check in `scripts/preflight.py`
- CI skeleton with separate unit/integration/soak jobs

## Quick Start (venv-first)

### Windows (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py
python -m tcp_sim --help
```

### Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py
python -m tcp_sim --help
```

## Test Commands

```bash
pytest -m unit -q
pytest -m integration -q
pytest -m soak -q
```

## Notes

- Runtime dependencies are stdlib-only for MVP.
- Development tooling is provided under the `dev` extra.
