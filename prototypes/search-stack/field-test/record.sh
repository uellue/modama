#!/bin/bash
# A copy of scripts/record.sh of the kaizen plugin 0.6.0-dev.2 (https://github.com/uellue/skills, branch
# field-tests-269), unchanged but for these two lines, so that the staging runbook runs without the plugin.
# Field-test recordings (the field-test skill, step 4: a view of the person's terminal for the agent).
#
#   record.sh            records into the next free run-<n> under ~/field-test (run-0 the first time), until `exit`;
#                        the run's folder also gets notes.md, your notes about the test
#   record.sh --next     only prints the folder the next recording would use
#   record.sh --pack [N] packs run-N (default: the latest) into ~/field-test/run-N.tar.gz, the run's evidence as one file
#
# Inside the recorded shell, FIELD_TEST_RUN is the run's folder.
#
# Written as it goes (-f), so a run can be followed live and survives a crash (run 0, 2026-11-09).
# The first time, it asks before creating ~/field-test (FIELD_TEST_DIR overrides it). Output and timing only:
# never --log-in, which would record every key, passwords included. An existing run folder is never reused;
# nothing is deleted.
set -euo pipefail
# The run folder and the archive are the owner's alone (on a shared machine others could read what the terminal
# showed); the recorded shell keeps the person's own umask, so the session itself is not changed.
base="${FIELD_TEST_DIR:-$HOME/field-test}"
case "$base" in /*) ;; *) base="$PWD/$base" ;; esac  # FIELD_TEST_RUN must stay valid after a cd

n=0
for d in "$base"/run-*; do
    [ -d "$d" ] || continue
    k="${d##*/run-}"
    case "$k" in '' | *[!0-9]*) continue ;; esac
    k=$((10#$k))
    [ "$k" -ge "$n" ] && n=$((k + 1))
done
run="$base/run-$n"

if [ "${1:-}" = "--pack" ]; then
    [ $# -le 2 ] || { echo "usage: record.sh --pack [N]" >&2; exit 2; }
    p="${2:-$((n - 1))}"
    [[ "$p" =~ ^[0-9]+$ ]] || { echo "usage: record.sh --pack [N]" >&2; exit 2; }
    [ -d "$base/run-$p" ] || { echo "no $base/run-$p" >&2; exit 1; }
    [ ! -e "$base/run-$p.tar.gz" ] || { echo "$base/run-$p.tar.gz exists already" >&2; exit 1; }
    (umask 077; tar -C "$base" -czf "$base/run-$p.tar.gz" "run-$p")
    echo "Packed: $base/run-$p.tar.gz ($(du -h "$base/run-$p.tar.gz" | cut -f1)). Look through it for anything private before sharing."
    exit 0
fi

if [ "${1:-}" = "--next" ]; then
    echo "$run"
    exit 0
fi
[ $# -eq 0 ] || { echo "usage: record.sh [--next | --pack [N]]" >&2; exit 2; }

if [ ! -d "$base" ]; then
    printf 'Create %s as the folder for field-test runs (recordings, notes, the evidence of each run)? [y/N] ' "$base"
    read -r answer || answer=""
    case "$answer" in y | Y | yes) ;; *) echo "Nothing created."; exit 1 ;; esac
    mkdir -p "$base"
fi
mkdir -m 700 "$run"  # private; fails rather than reuse a folder another terminal just took
printf '# Notes, %s\n\n' "${run##*/}" > "$run/notes.md"
echo "Recording into $run until you type exit. Output and timing only; look through session.log before sharing it."
echo "Notes: $run/notes.md, or at a shell prompt as comments, '# like this' (zsh: 'setopt interactivecomments' first). Not inside Claude."
export FIELD_TEST_RUN="$run"
exec script -q -f -T "$run/timing.log" -O "$run/session.log"
