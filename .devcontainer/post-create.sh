#!/bin/bash
set -euo pipefail

# The claude-home volume is created root-owned; hand it to the user, and
# restore a backup taken before a rebuild (see AGENTS.md) if the volume is empty.
sudo chown vscode:vscode ~/.claude
backup=/workspaces/data-management-system/.claude/home-backup
if [ ! -e ~/.claude/projects ] && [ -d "$backup" ]; then
    cp -a "$backup/." ~/.claude/
fi

python -m venv ~/.venv
~/.venv/bin/pip install --upgrade pip

# pyxdg is a local fork, installed in editable mode
~/.venv/bin/pip install \
    -e /workspaces/pyxdg \
    -e "/workspaces/data-management-system/python/crawler[test]" \
    ruff pre-commit
