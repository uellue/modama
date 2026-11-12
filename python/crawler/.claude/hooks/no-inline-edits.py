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

Flagged, not refused (@weber, 2026-11-11, to see where it triggers before
refining it): shell redirection (> or >>) or tee into a file other than
/dev/* or /tmp/*. The call goes ahead; the agent and the person see a note,
and the command is appended to FLAG_LOG.
"""

import json
import os
import re
import sys
from datetime import UTC, datetime

PATTERNS = [
    (r"\bsed\b[^|;&]*\s(-[a-zA-Z]*i|--in-place)", "sed -i"),
    (r"\bperl\b[^|;&]*\s-[a-zA-Z]*i", "perl -i"),
    (r"\.write_(text|bytes)\(", "inline Python write_text/write_bytes"),
    (
        r"\bopen\([^)]*,\s*['\"][rwax]*[wax+][a-z]*['\"]",
        "inline Python open() for writing",
    ),
]

# > or >> (not >&, not part of 2>&1), or tee, followed by a target path
REDIRECT = re.compile(r"(?:(?<![>&0-9])\d?>>?(?!&)|\btee\s+(?:-a\s+)?)\s*([^\s;|&)]+)")
FLAG_LOG = os.environ.get(
    "HOOK_FLAG_LOG", "/workspaces/data-management-system/.claude/hook-flags.log"
)


def redirect_targets(command: str) -> list[str]:
    return [
        t
        for t in REDIRECT.findall(command)
        if not t.strip("'\"").startswith(("/dev/", "/tmp/", "$"))
    ]


def main() -> int:
    command = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    if not ("/tmp/" in command and "/workspaces/" not in command):
        for pattern, name in PATTERNS:
            if re.search(pattern, command):
                print(
                    f"Refused ({name}): edit files with the Edit tool (or Write for new files), "
                    "not with shell commands, so that /rewind can undo the change. "
                    "Rule: python/crawler/AGENTS.md; hook: python/crawler/.claude/hooks/no-inline-edits.py.",
                    file=sys.stderr,
                )
                return 2
    targets = redirect_targets(command)
    if targets:
        note = (
            f"Flagged (shell write to {', '.join(targets)}): /rewind cannot undo it; "
            "for files in the repository prefer Edit or Write. Logged for refining the rule."
        )
        try:
            with open(FLAG_LOG, "a") as log:
                stamp = datetime.now(UTC).isoformat(timespec="seconds")
                log.write(f"{stamp}\t{targets}\t{command[:300]!r}\n")
        except OSError:
            pass
        print(
            json.dumps(
                {
                    "systemMessage": note,
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": note,
                    },
                }
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
