#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ ! -x .venv/bin/python ]; then
    "$PYTHON_BIN" -m venv .venv
fi
if ! .venv/bin/python - <<'PY'
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
try:
    for line in Path('requirements.txt').read_text().splitlines():
        if line.strip() and not line.startswith('#'):
            name, expected = line.split('==')
            if version(name) != expected:
                raise SystemExit(1)
except PackageNotFoundError:
    raise SystemExit(1)
PY
then
    .venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt
fi
exec .venv/bin/python -m streamlit run app.py "$@"
