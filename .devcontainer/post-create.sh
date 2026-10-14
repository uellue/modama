#!/bin/bash
set -euo pipefail

python -m venv ~/.venv
~/.venv/bin/pip install --upgrade pip

# pyxdg and oaipmh are local forks, installed in editable mode
~/.venv/bin/pip install \
    -e /workspaces/pyxdg \
    -e /workspaces/oaipmh \
    -e "/workspaces/data-management-system/python/crawler[test]" \
    ruff pre-commit
