#!/bin/bash
# The emulated production file system (design/requirements-benchmark.md, 2.1 and 80):
# exports BENCH_EXPORT over NFS 4.1 to this machine only and mounts it at BENCH_MOUNT
# with production's options (field-test finding F12: rsize 64 KiB, wsize 1 MiB, so
# st_blksize 1 MiB). BENCH_DELAY (for example 10ms) delays NFS packets in each
# direction on the loopback device, so a round trip gains about twice that; other
# traffic is not delayed. Root; safe to run again. nfs-down.sh undoes it.
#
#   sudo BENCH_DELAY=10ms ./nfs-up.sh
set -euo pipefail
export_dir=${BENCH_EXPORT:-/srv/modama-bench}
mnt=${BENCH_MOUNT:-/mnt/modama-bench}
delay=${BENCH_DELAY:-}

mkdir -p "$export_dir" "$mnt" /etc/exports.d
echo "$export_dir 127.0.0.1(ro,no_subtree_check,fsid=4711,insecure)" \
    > /etc/exports.d/modama-bench.exports
systemctl start nfs-server
exportfs -ra
mountpoint -q "$mnt" ||
    mount -t nfs4 -o ro,vers=4.1,rsize=65536,wsize=1048576 "127.0.0.1:$export_dir" "$mnt"

# Delay only NFS (port 2049): a prio qdisc whose fourth band gets no traffic by
# default, netem on that band, and filters that send port 2049 there.
tc qdisc del dev lo root 2>/dev/null || true
if [ -n "$delay" ]; then
    tc qdisc add dev lo root handle 1: prio bands 4
    tc qdisc add dev lo parent 1:4 handle 40: netem delay "$delay"
    tc filter add dev lo parent 1: protocol ip u32 match ip dport 2049 0xffff flowid 1:4
    tc filter add dev lo parent 1: protocol ip u32 match ip sport 2049 0xffff flowid 1:4
fi
echo "$export_dir exported, mounted at $mnt, delay per direction: ${delay:-none}"
