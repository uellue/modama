#!/bin/bash
# Undoes nfs-up.sh: removes the delay, unmounts and unexports. The exported tree stays.
# Root.
set -uo pipefail
mnt=${BENCH_MOUNT:-/mnt/modama-bench}
tc qdisc del dev lo root 2>/dev/null
mountpoint -q "$mnt" && umount "$mnt"
rm -f /etc/exports.d/modama-bench.exports
exportfs -ra
echo "unmounted $mnt, export and delay removed"
