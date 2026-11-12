#!/bin/bash
# Copy ~/.claude (Claude Code sessions, memory, plugins) into the repository's
# gitignored .claude/home-backup/, so that post-create.sh can restore it into
# an empty claude-home volume after a rebuild. The login credential stays out:
# a checkout is no place for it, and `claude` asks to log in again if needed.
set -euo pipefail
backup=/workspaces/data-management-system/.claude/home-backup
mkdir -p "$backup"
rsync -a --delete --exclude .credentials.json ~/.claude/ "$backup/"
echo "backed up ~/.claude to $backup (without .credentials.json)"
