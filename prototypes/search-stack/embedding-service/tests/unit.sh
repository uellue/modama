#!/bin/bash
# modama-embed.service in a throwaway systemd container, on the CPU (change
# embedding-service-grace, task 2.4): the README's `run: grace` blocks as written, with
# three things changed for an x86 container without a GPU: the venv from
# requirements-cpu.txt with Debian's Python, the device set to cpu by a drop-in, the limit
# filled in. Then one PASS/FAIL line per check; exit 1 if any failed.
#
#   tests/unit.sh
#
# Docker and access to pypi.org and huggingface.co needed; the container and image are
# removed at the end. About 3 minutes.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
service_dir="$(dirname "$here")"
repo="$(cd "$service_dir/../../.." && pwd)"
p="embedunit-$$"
FAILED=0
cleanup() {
    docker rm -f "$p" > /dev/null 2>&1
    docker image rm "$p" > /dev/null 2>&1
}
trap cleanup EXIT
check() {  # what, command...
    local what=$1 out
    shift
    if out=$("$@" 2>&1); then
        echo "PASS  $what"
    else
        echo "FAIL  $what"
        [ -n "$out" ] && echo "$out" | tail -n 8 | sed 's/^/        /'
        FAILED=1
    fi
}
block() {  # the README's Nth `run: grace` block
    awk -v n="$1" '
        $0 == "<!-- run: grace -->" { k++; want = (k == n); next }
        want && /^```bash$/ { inside = 1; next }
        inside && /^```$/ { inside = 0; want = 0; next }
        inside { print }' "$service_dir/README.md"
}
c() { docker exec -i "$p" "$@"; }

docker build -q -t "$p" -f "$repo/deploy/ssh-tunnel/test/host.Dockerfile" "$repo/deploy/ssh-tunnel/test" > /dev/null || exit 2
docker run -d --name "$p" --privileged -v "$service_dir:/src:ro" "$p" > /dev/null || exit 2
for _ in $(seq 30); do
    c systemctl is-system-running 2> /dev/null | grep -qE 'running|degraded' && break
    sleep 1
done

# the README's blocks, in its order
check "README: the venv (here requirements-cpu.txt with Debian's Python)" \
    sh -c "sed -e 's|python3.12 -m venv|python3 -m venv|' -e 's|requirements-gpu.txt|requirements-cpu.txt|' <<'EOF' | docker exec -i $p bash -ec 'cd /src; . /dev/stdin'
$(block 1)
EOF"
check "README: the account, the service's file and the model files" \
    sh -c "docker exec -i $p bash -ec 'cd /src; . /dev/stdin' <<'EOF'
$(block 2)
EOF"
c sh -ec 'mkdir -p /etc/systemd/system/modama-embed.service.d
    printf "[Service]\nEnvironment=MODAMA_EMBED_DEVICE=cpu\n" > /etc/systemd/system/modama-embed.service.d/device.conf'
check "README: the token, the unit and the limit; enabled" \
    sh -c "sed 's|^limit=.*|limit=2000000000|' <<'EOF' | docker exec -i $p bash -ec 'cd /src; . /dev/stdin'
$(block 3)
EOF"

check "systemd-analyze verify" c systemd-analyze verify modama-embed.service
up() {
    for _ in $(seq 90); do
        c curl -sf http://127.0.0.1:7656/health && return 0
        sleep 1
    done
    c journalctl -u modama-embed --no-pager | tail -n 20
    return 1
}
check "the service answers /health (CPUExecutionProvider here)" up
check "its processes run as modama-embed" \
    c sh -c '[ "$(ps -o user:16= -C python,python3 | sort -u)" = modama-embed ] || { ps -o user:16=,args= -C python,python3; exit 1; }'
check "it listens on 127.0.0.1:7656 only" \
    c sh -c 'ss -ltn | grep -q "127.0.0.1:7656 " && ! ss -ltn | grep ":7656 " | grep -qv "127.0.0.1:7656 "'
ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$p")
check "from another host (this VM to the container's address): refused" \
    sh -c "! curl -s -m 5 http://$ip:7656/health"
check "the token file is root's, mode 600" c sh -c '[ "$(stat -c %U:%a /etc/modama-embed/token)" = root:600 ]'
marker="MARKER-$$-not-logged"
check "a request with the token: 200; the journal has its line, not the text or the token" \
    c sh -ec "t=\$(cat /etc/modama-embed/token)
        curl -sf -o /dev/null -H \"Authorization: Bearer \$t\" -H 'Content-Type: application/json' \
            -d '{\"model\": \"bge-small-en-v1.5\", \"input\": [\"ferritin $marker\"]}' http://127.0.0.1:7656/v1/embeddings
        sleep 1
        j=\$(journalctl -u modama-embed --no-pager)
        echo \"\$j\" | grep -q 'status=200 texts=1'
        ! echo \"\$j\" | grep -q -e '$marker' -e \"\$t\""
check "the process is killed: started again after 30 s, /health within a minute" \
    c sh -ec 'pid=$(systemctl show -p MainPID --value modama-embed); kill -9 "$pid"; sleep 2
        for i in $(seq 60); do curl -sf -o /dev/null http://127.0.0.1:7656/health && [ "$(systemctl show -p MainPID --value modama-embed)" != "$pid" ] && exit 0; sleep 1; done; exit 1'
c sh -c 'rm /etc/systemd/system/modama-embed.service.d/*.conf && systemctl daemon-reload && systemctl restart modama-embed'
sleep 3
check "without a memory limit (on the GPU) it refuses to start, saying why" \
    sh -c "docker exec $p journalctl -u modama-embed --no-pager | grep 'MODAMA_EMBED_MEM_LIMIT is not set'"
exit $FAILED
