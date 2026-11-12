#!/bin/bash
# Watch the staging deployment: every INTERVAL seconds (default 30), append to LOG the
# load, memory, disk use of / and of Docker's root, each container's CPU, memory and
# I/O, the crawls, and modama-chain status. Reads only; stop it with Ctrl-C.
#
#   monitor.sh LOG [INTERVAL]
set -uo pipefail
cd "$(dirname "$0")"
log=${1:?usage: monitor.sh LOG [INTERVAL]}
interval=${2:-30}
dc() { docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml "$@"; }
docker_root=$(docker info -f '{{.DockerRootDir}}')
echo "monitoring into $log every ${interval}s; Ctrl-C to stop"
while true; do
    {
        echo "=== $(date -u +%FT%TZ)  $(cut -d' ' -f1-3 /proc/loadavg) load"
        free -g | sed -n 2p
        df -h --output=target,size,used,avail,pcent / "$docker_root" | sed 1d
        # a warning line when / or Docker's root is more than 90% full
        df --output=pcent,target / "$docker_root" | sed 1d \
            | awk '{sub("%", "", $1); if ($1 > 90) print "WARNING: " $2 " is " $1 "% full"}'
        docker stats --no-stream --format '{{.Name}} cpu={{.CPUPerc}} mem={{.MemUsage}} io={{.BlockIO}}' \
            | grep '^search-staging' | sed 's/^search-staging-//'
        dc exec -T crawl-timer modama-crawler runs 2>&1 | head -n 4
        dc exec -T crawler modama-chain status 2>&1
    } >> "$log"
    sleep "$interval"
done
