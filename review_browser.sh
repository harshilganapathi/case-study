#!/usr/bin/env sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from playwright.sync_api import sync_playwright' 2>/dev/null; then
    .venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements-browser.txt
fi
exec .venv/bin/python scripts/browser_review.py "$@"
