#!/usr/bin/env python3
"""PreToolUse hook (Bash): refuse commands that edit files in place.

Edits made by a shell command bypass Claude Code's file checkpoints, so
/rewind cannot undo them; the Edit tool can. Rule in python/crawler/AGENTS.md
("edit files with the Edit tool, not with inline replacement scripts"),
enforced here since the debrief of 2026-11-11 (design/kaizen.md, proposal 7).

Refused: sed -i, perl -i, and inline Python that writes files
(write_text, write_bytes, open(..., 'w'/'a'/'x')). Allowed when the command
touches only /tmp (the session scratchpad) and nothing under /workspaces.
Exit 2 blocks the call and shows stderr to the agent.
"""

import json
import re
import sys

PATTERNS = [
    (r"\bsed\b[^|;&]*\s(-[a-zA-Z]*i|--in-place)", "sed -i"),
    (r"\bperl\b[^|;&]*\s-[a-zA-Z]*i", "perl -i"),
    (r"\.write_(text|bytes)\(", "inline Python write_text/write_bytes"),
    (
        r"\bopen\([^)]*,\s*['\"][rwax]*[wax+][a-z]*['\"]",
        "inline Python open() for writing",
    ),
]


def main() -> int:
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    if "/tmp/" in command and "/workspaces/" not in command:
        return 0
    for pattern, name in PATTERNS:
        if re.search(pattern, command):
            print(
                f"Refused ({name}): edit files with the Edit tool (or Write for new files), "
                "not with shell commands, so that /rewind can undo the change. "
                "Rule: python/crawler/AGENTS.md; hook: python/crawler/.claude/hooks/no-inline-edits.py.",
                file=sys.stderr,
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
