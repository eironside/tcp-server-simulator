E:
cd E:\Git\tcp-server-simulator
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .[dev]
python scripts/preflight.py
