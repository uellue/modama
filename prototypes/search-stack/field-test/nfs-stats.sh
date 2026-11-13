#!/bin/bash
# NFS counters of the mount that holds PATH (the data tree), for the performance baseline
# (finding F5: docker stats does not see NFS reads). Every INTERVAL seconds (default 60)
# appends a time stamp and the mount's block of /proc/self/mountstats (bytes read,
# operations with their counts and round-trip times) to LOG. Reads only; Ctrl-C stops it.
# nfsdelta.py turns the log into rates per interval.
#
#   nfs-stats.sh PATH LOG [INTERVAL]
#   e.g. nfs-stats.sh /mnt/modama-bench /var/tmp/nfs.log 10
set -uo pipefail
usage="usage: nfs-stats.sh PATH LOG [INTERVAL]"
path=${1:?$usage}
log=${2:?$usage}
interval=${3:-60}
mnt=$(findmnt -n -o TARGET -T "$path")
echo "NFS counters of $mnt into $log every ${interval}s; Ctrl-C to stop"
while true; do
    {
        echo "=== $(date -u +%FT%TZ) $mnt"
        awk -v m="$mnt" '$1 == "device" {on = ($5 == m)} on' /proc/self/mountstats
    } >> "$log"
    sleep "$interval"
done
