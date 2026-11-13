#!/bin/bash
# Tests of ssh-tunnel@.service and its README (change embedding-service-grace, tasks 4.1 to
# 4.4): two throwaway containers, a client with systemd and a far end with sshd (OpenSSH of
# Debian 13), the README's `run:` blocks run as written (the far end's key and host name
# filled in), then one PASS/FAIL line per scenario of the spec `ssh-tunnel`. Exit 1 if any
# failed. About 5 minutes; Docker needed; the containers, network and image are removed.
#
#   deploy/ssh-tunnel/test/run.sh
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tunnel="$(dirname "$here")"
p="sshtt-$$"
client="$p-client" farend="$p-farend" image="$p-host"
FAILED=0

cleanup() {
    docker rm -f "$client" "$farend" > /dev/null 2>&1
    docker network rm "$p" > /dev/null 2>&1
    docker image rm "$image" > /dev/null 2>&1
}
trap cleanup EXIT

check() {  # what, command...
    local what=$1 out
    shift
    if out=$("$@" 2>&1); then
        echo "PASS  $what"
    else
        echo "FAIL  $what"
        [ -n "$out" ] && echo "$out" | head -n 8 | sed 's/^/        /'
        FAILED=1
    fi
}

# the README's Nth `run: ROLE` block (1-based)
block() {
    awk -v role="$1" -v n="$2" '
        $0 == "<!-- run: " role " -->" { k++; want = (k == n); next }
        want && /^```bash$/ { inside = 1; next }
        inside && /^```$/ { inside = 0; want = 0; next }
        inside { print }' "$tunnel/README.md"
}
c() { docker exec -i "$client" "$@"; }
f() { docker exec -i "$farend" "$@"; }

docker build -q -t "$image" -f "$here/host.Dockerfile" "$here" > /dev/null || exit 2
docker network create "$p" > /dev/null || exit 2
docker run -d --name "$farend" --hostname farend --network "$p" "$image" sleep infinity > /dev/null
# privileged for systemd; the default unprivileged port start, as on a host (Docker sets 0)
docker run -d --name "$client" --hostname client --network "$p" --privileged \
    --sysctl net.ipv4.ip_unprivileged_port_start=1024 \
    -v "$tunnel:/src/deploy/ssh-tunnel:ro" "$image" > /dev/null
for _ in $(seq 30); do
    c systemctl is-system-running 2> /dev/null | grep -qE 'running|degraded' && break
    sleep 1
done
start_farend() {
    f sh -c '/usr/sbin/sshd -E /var/log/sshd.log
        cd /tmp && (python3 -m http.server 7656 --bind 127.0.0.1 > /dev/null 2>&1 &)
        (python3 -m http.server 11434 --bind 127.0.0.1 > /dev/null 2>&1 &)'
}
f ssh-keygen -A > /dev/null
c ip addr add 172.17.0.1/32 dev lo   # Docker's bridge address, as on the staging host

# the README, in its order
block client 1 | c bash -e > /dev/null 2>&1 ||{ echo "FAIL  README: the client's account and key"; exit 1; }
key=$(c cat /etc/ssh-tunnel/embed/key.pub)
block farend 1 | sed "s|^key=.*|key='$key'|" \
    | f bash -ec 'systemctl() { :; }; . /dev/stdin' > "/var/tmp/$p-farend.out" 2>&1
farend_ok=$?
[ "$farend_ok" = 0 ] || cat "/var/tmp/$p-farend.out"
start_farend
block client 2 | sed 's|^host=.*|host=farend|' | c bash -e > /dev/null 2>&1
conf_ok=$?
block client 3 | c bash -ec 'cd /src; . /dev/stdin' > /dev/null 2>&1
install_ok=$?
check "README: the far end's account, key line and Match block (sshd -t)" test "$farend_ok" = 0
check "README: the host key and the instance's file" test "$conf_ok" = 0
check "README: install and enable" test "$install_ok" = 0
sleep 3

# Requirement: One instance per tunnel, configured outside the unit
check "systemd-analyze verify of the instance" c systemd-analyze verify ssh-tunnel@embed.service
check "the grace tunnel as an instance: ssh -N with both forwards, as ssh-tunnel" \
    c sh -c 'systemctl is-active ssh-tunnel@embed &&
        ps -o user:16=,args= -C ssh | grep -E "^ssh-tunnel +/usr/bin/ssh .* -N.*-L 172.17.0.1:17656:127.0.0.1:7656 -L 172.17.0.1:11434:127.0.0.1:11434 embedtunnel@farend"'
check "two permitted destinations: both forwards answer" \
    c sh -c 'curl -sf -o /dev/null http://172.17.0.1:17656/ && curl -sf -o /dev/null http://172.17.0.1:11434/'

# Requirement: The key opens nothing but its forwards (with the instance's key, as root)
k="-F none -i /etc/ssh-tunnel/embed/key -o UserKnownHostsFile=/etc/ssh-tunnel/embed/known_hosts -o BatchMode=yes"
check "a shell: This account is currently not available." \
    c sh -c "ssh $k embedtunnel@farend id -un 2>&1 | grep -x 'This account is currently not available.'"
f usermod -s /bin/bash embedtunnel
check "a shell after the account's shell was changed: the forced command answers" \
    c sh -c "out=\$(ssh $k embedtunnel@farend id -un 2>&1); echo \"\$out\"; [ \"\$out\" = 'This account is currently not available.' ]"
f usermod -s /usr/sbin/nologin embedtunnel
check "a terminal: PTY allocation request failed" \
    c sh -c "timeout 10 ssh $k -tt embedtunnel@farend < /dev/null 2>&1 | grep 'PTY allocation request failed'"
forward_refused() {  # local port, forward target
    c sh -c "ssh $k -N -L 127.0.0.1:$1:$2 embedtunnel@farend & pid=\$!; sleep 2
        out=\$(curl -s -m 5 http://127.0.0.1:$1/ 2>&1); rc=\$?; kill \$pid; [ \$rc -ne 0 ]" &&
        f grep -qE "$3" /var/log/sshd.log
}
check "another destination (-L 9000:127.0.0.1:22): refused, in sshd's log" \
    forward_refused 9000 127.0.0.1:22 'to connect to host 127.0.0.1 port 22, but the request was denied'
check "the permitted port by another name (localhost): refused" \
    forward_refused 9002 localhost:7656 'to connect to host localhost port 7656, but the request was denied'
check "a forward to a Unix socket on the destination: refused, in sshd's log" \
    forward_refused 9001 /run/some.socket 'refused streamlocal port forward: .* target /run/some.socket'
check "a remote forward: remote port forwarding failed, nothing listens on 9000" \
    sh -c "docker exec $client sh -c \"timeout 15 ssh $k -o ExitOnForwardFailure=yes -N -R 127.0.0.1:9000:127.0.0.1:22 embedtunnel@farend 2>&1\" | grep 'remote port forwarding failed for listen port 9000' &&
        ! docker exec $farend sh -c 'ss -ltn | grep -q :9000'"
check "a Unix socket created on the destination: refused, no socket" \
    sh -c "docker exec $client sh -c \"timeout 15 ssh $k -o ExitOnForwardFailure=yes -N -R /tmp/x.socket:127.0.0.1:22 embedtunnel@farend 2>&1\" | grep -i 'remote port forwarding failed' &&
        ! docker exec $farend test -e /tmp/x.socket"
check "what applies on the destination's sshd (sshd -T -C user=embedtunnel)" \
    f sh -c 'out=$(sshd -T -C user=embedtunnel); echo "$out" | grep -x "allowtcpforwarding local" &&
        echo "$out" | grep -x "allowstreamlocalforwarding no" && echo "$out" | grep -x "permittty no" &&
        echo "$out" | grep -x "x11forwarding no" && echo "$out" | grep -x "permitopen 127.0.0.1:7656 127.0.0.1:11434"'

# an instance next to embed: its own file and folder, the key and host key copied
instance() {  # name, DESTINATION, FORWARDS, known hosts (copy|empty)
    c sh -ec "install -d -m 700 -o ssh-tunnel -g ssh-tunnel /etc/ssh-tunnel/$1
        install -m 600 -o ssh-tunnel -g ssh-tunnel /etc/ssh-tunnel/embed/key /etc/ssh-tunnel/$1/key
        if [ $4 = copy ]; then cp /etc/ssh-tunnel/embed/known_hosts /etc/ssh-tunnel/$1/; else : > /etc/ssh-tunnel/$1/known_hosts; fi
        chown ssh-tunnel:ssh-tunnel /etc/ssh-tunnel/$1/known_hosts
        printf 'DESTINATION=%s\nFORWARDS=%s\nSSH_OPTIONS=\n' '$2' '$3' > /etc/ssh-tunnel/$1.conf
        systemctl start ssh-tunnel@$1"
}
journal() { c journalctl -q -u "ssh-tunnel@$1" --no-pager -o short-unix; }

# Requirement: The tunnel fails instead of asking or hanging
c sh -c 'printf "Host *\n    StrictHostKeyChecking no\n    IdentityFile /etc/ssh-tunnel/none\n" >> /etc/ssh/ssh_config'
instance unknown embedtunnel@farend "-L 127.0.0.1:17701:127.0.0.1:7656" empty
sleep 3
check "an unknown host key, with a system ssh_config saying StrictHostKeyChecking no: refused at once" \
    sh -c "docker exec $client journalctl -q -u ssh-tunnel@unknown --no-pager | grep 'Host key verification failed'"
c systemctl stop ssh-tunnel@unknown
instance silent embedtunnel@10.255.255.1 "-L 127.0.0.1:17702:127.0.0.1:7656" copy
sleep 45
check "the destination does not answer: ends within 10 s, tried again 30 s later" \
    sh -c "j=\$(docker exec $client journalctl -q -u ssh-tunnel@silent --no-pager -o short-unix); echo \"\$j\"
        echo \"\$j\" | grep -q 'Connection timed out' &&
        starts=\$(echo \"\$j\" | awk '/Started ssh-tunnel@silent/ {print \$1}'); ends=\$(echo \"\$j\" | awk '/Connection timed out/ {print \$1}')
        set -- \$starts; s1=\$1 s2=\${2:-0}; set -- \$ends; e1=\$1
        awk -v s1=\$s1 -v s2=\$s2 -v e1=\$e1 'BEGIN { exit !(e1 - s1 <= 11 && s2 - e1 >= 29 && s2 - e1 <= 33) }'"
c systemctl stop ssh-tunnel@silent

# Requirement: The tunnel ends when a forward cannot be set up
c sh -c '(python3 -m http.server 17703 --bind 127.0.0.1 > /dev/null 2>&1 &)'
sleep 1
instance taken embedtunnel@farend "-L 127.0.0.1:17703:127.0.0.1:7656" copy
sleep 35
check "the local port is taken: ssh ends naming the port, started again after 30 s" \
    sh -c "j=\$(docker exec $client journalctl -q -u ssh-tunnel@taken --no-pager); echo \"\$j\" | grep -q 'cannot listen to port: 17703' &&
        [ \$(echo \"\$j\" | grep -c 'Started ssh-tunnel@taken') -ge 2 ]"
c systemctl stop ssh-tunnel@taken

# Requirement: The tunnel comes back by itself (the far end's sshd gone for 60 s)
f pkill sshd   # the listener and the sessions (sshd-session)
sleep 60
start_farend
up() {
    for _ in $(seq 45); do
        c curl -sf -o /dev/null http://172.17.0.1:17656/ && return 0
        sleep 1
    done
    return 1
}
check "the far end gone and back: the tunnel works again within 45 s, without anyone acting" up

# Requirement (before production): The tunnel's address cannot be taken while it is down
c sh -ec 'mkdir -p /etc/systemd/system/ssh-tunnel@priv.service.d
    printf "[Service]\nAmbientCapabilities=CAP_NET_BIND_SERVICE\n" > /etc/systemd/system/ssh-tunnel@priv.service.d/port.conf
    systemctl daemon-reload'
instance priv embedtunnel@farend "-L 172.17.0.1:755:127.0.0.1:7656" copy
sleep 3
check "before production: a port below 1024 with the drop-in answers" c curl -sf -o /dev/null http://172.17.0.1:755/
c systemctl stop ssh-tunnel@priv
check "before production: the instance stopped, an unprivileged user cannot listen there" \
    c sh -c "setpriv --reuid=nobody --regid=nogroup --clear-groups python3 -c 'import socket; socket.socket().bind((\"172.17.0.1\", 755))' 2>&1 | grep 'Permission denied'"

rm -f "/var/tmp/$p-farend.out"
exit $FAILED
