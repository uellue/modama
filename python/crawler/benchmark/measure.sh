#!/bin/bash
# What NFS did for one command: the mount's counters (/proc/self/mountstats) before and
# after, per operation the count, megabytes received and average round trip, and the
# wall time. Reads only; no root. The counters are the whole machine's for that mount,
# so others using it at the same time count too. The command's output goes to /dev/null.
#
#   measure.sh MOUNT COMMAND [ARG...]
set -euo pipefail
[ $# -ge 2 ] || { echo "usage: $0 MOUNT COMMAND [ARG...]" >&2; exit 2; }
mnt=$(findmnt -n -o TARGET -T "$1")
shift

stats() { awk -v m="$mnt" '$1 == "device" {on = ($5 == m)} on && $1 ~ /^[A-Z_]+:$/ && NF >= 9' /proc/self/mountstats; }
before=$(stats)
start=$(date +%s.%N)
status=0
"$@" > /dev/null || status=$?
end=$(date +%s.%N)
after=$(stats)

echo "command: $*"
awk -v a="$start" -v b="$end" -v m="$mnt" -v s="$status" \
    'BEGIN {printf "wall time: %.2f s, exit status %d, mount %s\n", b - a, s, m}'
echo "NFS operation      count   MB received   avg round trip (ms)"
# Each line: the operation, then count, transmissions, timeouts, bytes sent, bytes
# received, queue, round-trip and execution time in ms (cumulative), errors.
paste <(echo "$before") <(echo "$after") | awk '{
    n = $12 - $2; if (n <= 0) next
    printf "%-16s %8d %13.1f %21.2f\n", $1, n, ($16 - $6) / 1e6, ($18 - $8) / n }'
exit "$status"
