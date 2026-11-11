#!/bin/bash
# One measured run of any command against the emulated file system (nfs-up.sh), from
# outside the program (design/requirements-benchmark.md, 75): remounts first, so that
# the client's cache is cold, runs the command as the calling user in a cgroup limited
# to BENCH_MEMORY (default 256M, the small cache), and prints what NFS did (per
# operation: count, bytes received, round-trip time; measure.sh) and the cgroup's memory
# counters.
# Root (sudo); the command runs as $SUDO_USER, its output goes to /dev/null.
#
#   sudo ./run.sh modama-crawler records /mnt/modama-bench/smoke
set -euo pipefail
mnt=${BENCH_MOUNT:-/mnt/modama-bench}
memory=${BENCH_MEMORY:-256M}
user=${SUDO_USER:?run with sudo}
[ $# -gt 0 ] || { echo "usage: sudo $0 COMMAND [ARG...]" >&2; exit 2; }

src=$(findmnt -n -o SOURCE "$mnt")
opts=$(findmnt -n -o OPTIONS "$mnt" | grep -o 'ro\|vers=[^,]*\|rsize=[^,]*\|wsize=[^,]*' | paste -sd,)
umount "$mnt"
mount -t nfs4 -o "$opts" "$src" "$mnt"

memfile=$(mktemp)
chown "$user" "$memfile"
# The command runs in a transient scope; its last step, still inside, saves the
# cgroup's counters, which disappear with the scope.
"$(dirname "$0")/measure.sh" "$mnt" \
    systemd-run --quiet --scope -p MemoryMax="$memory" --uid="$user" --gid="$(id -g "$user")" \
    -- bash -c '"$@" > /dev/null; s=$?; cg=/sys/fs/cgroup$(cut -d: -f3 /proc/self/cgroup); cat "$cg/memory.stat" "$cg/memory.peak" > '"$memfile"'; exit $s' _ "$@"
echo "memory limit $memory"
awk '/^(anon|file) / {printf "%s %.1f MB\n", $1, $2 / 1e6}
     /^workingset_refault_file / {print "re-read after eviction:", $2, "pages"}
     NF == 1 {printf "memory.peak %.1f MB\n", $1 / 1e6}' "$memfile"
rm -f "$memfile"
