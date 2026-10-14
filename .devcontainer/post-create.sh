#!/bin/bash
set -euo pipefail

python -m venv ~/.venv
~/.venv/bin/pip install --upgrade pip

# pyxdg is a local fork, installed in editable mode
~/.venv/bin/pip install \
    -e /workspaces/pyxdg \
    -e "/workspaces/data-management-system/python/crawler[test]" \
    ruff pre-commit
