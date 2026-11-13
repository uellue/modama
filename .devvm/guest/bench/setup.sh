#!/bin/bash
# One-time setup of the crawl benchmark's tools in the VM (Debian 13): the NFS server and
# client for the emulated production mount (python/crawler/benchmark/nfs-up.sh), tc for its
# delay, and the tools for looking at I/O, the page cache and the kernel. The list is
# python/crawler/design/requirements-benchmark.md, 2.7; strace and perf come with the
# provisioning. Run through `devvm bench-setup`.
set -euo pipefail

sudo DEBIAN_FRONTEND=noninteractive apt-get -qq update
sudo DEBIAN_FRONTEND=noninteractive apt-get -qq install -y --no-install-recommends \
    nfs-kernel-server nfs-common iproute2 \
    bpftrace bpfcc-tools hyperfine vmtouch util-linux-extra fio sysstat > /dev/null
echo "benchmark setup done; next: python/crawler/benchmark/README.md, \"Setup\""
