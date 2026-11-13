# SSH tunnels: `ssh-tunnel@.service`

A systemd template for the SSH tunnels modama runs between hosts (`ssh -N -L`): one instance
per tunnel, configured in `/etc/ssh-tunnel/NAME.conf`, run as the account `ssh-tunnel`,
restarted 30 s after any failure. On the far end, the key opens nothing but its forwards.
Derived from `deploy/beatepi/etc/systemd/system/er-c-data-smb.service` and the grace tunnel of
`prototypes/search-stack/embedding-on-grace.md` (change `embedding-service-grace` in
`python/crawler/openspec/changes/`, design D7, spec `ssh-tunnel`).

Setting up a tunnel, in order: the client's account and key, the far end's account with the
key, the far end's host key on the client, the instance's file, enable. The commands below set
up the grace tunnel; for another tunnel change the variables at the top of each block. The
test (`test/run.sh`, below) runs the blocks marked `run:` as written.

## On the client (the host that needs the forwards), as root

The account, once per host, and a key per tunnel, made here and never copied elsewhere:

<!-- run: client -->
```bash
name=embed                                   # the instance: ssh-tunnel@embed
getent passwd ssh-tunnel || useradd --system --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin ssh-tunnel
install -d -m 700 -o ssh-tunnel -g ssh-tunnel "/etc/ssh-tunnel/$name"
ssh-keygen -q -t ed25519 -N '' -C "$(hostname)-$name-tunnel" -f "/etc/ssh-tunnel/$name/key"
chown ssh-tunnel:ssh-tunnel "/etc/ssh-tunnel/$name/key" "/etc/ssh-tunnel/$name/key.pub"
cat "/etc/ssh-tunnel/$name/key.pub"          # for the far end's authorized_keys, below
```

## On the far end (the destination), as root

An account of its own with no shell, the key with its restrictions, and a `Match` block for
the account at the end of `sshd_config` (not in `sshd_config.d/`: a `Match` there would also
capture the main file's lines that follow the `Include`):

<!-- run: farend -->
```bash
account=embedtunnel                          # the tunnel's account on this host
key='ssh-ed25519 AAAA... staging-embed-tunnel'   # the client's key.pub, one line
useradd --system --create-home --shell /usr/sbin/nologin "$account"
home=$(getent passwd "$account" | cut -d: -f6)
install -d -m 700 -o "$account" -g "$account" "$home/.ssh"
printf 'restrict,port-forwarding,permitopen="127.0.0.1:7656",permitopen="127.0.0.1:11434",command="/usr/sbin/nologin" %s\n' "$key" > "$home/.ssh/authorized_keys"
chown "$account:$account" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"
cat >> /etc/ssh/sshd_config <<EOF

Match User $account
    AllowTcpForwarding local
    AllowStreamLocalForwarding no
    PermitOpen 127.0.0.1:7656 127.0.0.1:11434
    PermitTTY no
    X11Forwarding no
EOF
sshd -t && systemctl reload ssh
sshd -T -C user="$account" | grep -E '^(allowtcpforwarding|allowstreamlocalforwarding|permittty|x11forwarding|permitopen) '
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub   # the fingerprint, for the client's check below
```

`sshd -T -C user=…` must show `allowtcpforwarding local`, `allowstreamlocalforwarding no`,
`permittty no`, `x11forwarding no` and `permitopen` with exactly the permitted destinations.

What each part does (sshd(8), "AUTHORIZED_KEYS FILE FORMAT", and sshd_config(5); checked with
OpenSSH 10.0, design D7, and by `test/run.sh`):

| Part | What it does | Without it |
|---|---|---|
| shell `/usr/sbin/nologin` | no shell, no command: `This account is currently not available.` | a command runs: `restrict` does not stop commands |
| `command="/usr/sbin/nologin"` | the same answer to any command, even if the account's shell is changed by mistake; `ssh -N` asks for no command, so the tunnel never runs it | a changed shell runs commands |
| `restrict` | no port, agent or X11 forwarding, no terminal, no `~/.ssh/rc` | all of them allowed |
| `port-forwarding` | port forwarding back on, in both directions | no tunnel |
| `permitopen="HOST:PORT"`, once per destination | `ssh -L` only to these, compared literally: `localhost` is not `127.0.0.1` | `-L` to anywhere the far end reaches |
| `AllowTcpForwarding local` | no remote forwards (`ssh -R`): `permitopen` does not limit them | someone with the key listens on the far end's ports or creates Unix sockets there |
| `AllowStreamLocalForwarding no`, `PermitOpen`, `PermitTTY no`, `X11Forwarding no` | the same limits on the server's side, whatever the key line says | only the key line holds them |

Optional, and recommended: `from="<client's address>"` at the start of the key line, so that
the key works only from the client ("either the canonical name of the remote host or its IP
address must be present", sshd(8)).

## Back on the client: the far end's host key and the instance

The far end's host key, checked against the fingerprint read on the far end itself (above),
not accepted blindly:

<!-- run: client -->
```bash
name=embed
host=grace.example                           # the far end's host name, as in DESTINATION
ssh-keyscan -t ed25519 "$host" > "/etc/ssh-tunnel/$name/known_hosts"
ssh-keygen -lf "/etc/ssh-tunnel/$name/known_hosts"   # must equal the far end's fingerprint
chown ssh-tunnel:ssh-tunnel "/etc/ssh-tunnel/$name/known_hosts"
cat > "/etc/ssh-tunnel/$name.conf" <<EOF
DESTINATION=embedtunnel@$host
FORWARDS=-L 172.17.0.1:17656:127.0.0.1:7656 -L 172.17.0.1:11434:127.0.0.1:11434
SSH_OPTIONS=
EOF
```

`FORWARDS` holds any number of `-L` (split at spaces), `SSH_OPTIONS` any other options of
ssh (empty adds nothing; beatepi's `-c aes128-ctr` would go here, a port other than 22 as
`-p 2222`). The address on the client's side must exist when the tunnel starts: Docker's
bridge address `172.17.0.1` exists only once Docker runs (drop-in below).

## Install, enable, logs

From a checkout of the repository, as root on the client:

<!-- run: client -->
```bash
name=embed
install -m 644 deploy/ssh-tunnel/ssh-tunnel@.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now "ssh-tunnel@$name"
systemctl status --no-pager "ssh-tunnel@$name"
```

```bash
journalctl -u ssh-tunnel@embed -f            # its log
systemctl disable --now ssh-tunnel@embed     # stop it and keep it stopped
```

The tunnel fails instead of asking or hanging: an unknown or changed host key or a refused
key end `ssh` at once (`BatchMode`, `StrictHostKeyChecking`), a far end that does not answer
within 10 s (`ConnectTimeout`), a forward that cannot be set up (`ExitOnForwardFailure`, for
example a local port taken). systemd starts it again 30 s later, without a limit. A
connection that stops answering ends after about 3 minutes (`ServerAliveInterval=60`, 3
missed). No `ssh_config` of the account or the system applies (`-F none`), and only the
instance's key is offered (`IdentitiesOnly`).

## Drop-ins

`systemctl edit ssh-tunnel@embed` (one instance) or `systemctl edit ssh-tunnel@` (all):

```ini
[Unit]
# a forward on Docker's bridge address: start after Docker
After=docker.service
```

```ini
[Service]
# a forward on a port below 1024: no unprivileged user can listen there while the tunnel is
# down (before anything beyond a demo; embedding-on-grace.md, "Before anything beyond the demo")
AmbientCapabilities=CAP_NET_BIND_SERVICE
```

The port below 1024 needs the far end's `permitopen` and `PermitOpen` to match, and
`net.ipv4.ip_unprivileged_port_start` at its default of 1024.

## The checks by hand

From the client, with the instance's key, each must be refused (spec `ssh-tunnel`, "The key
opens nothing but its forwards"):

```bash
k="-F none -i /etc/ssh-tunnel/embed/key -o UserKnownHostsFile=/etc/ssh-tunnel/embed/known_hosts"
ssh $k embedtunnel@grace.example id -un        # This account is currently not available.
ssh $k -tt embedtunnel@grace.example           # PTY allocation request failed
ssh $k -N -R 127.0.0.1:47656:127.0.0.1:22 embedtunnel@grace.example   # remote port forwarding failed
ssh $k -N -R /tmp/x.socket:127.0.0.1:22 embedtunnel@grace.example     # remote port forwarding failed
ssh $k -N -L 127.0.0.1:9000:127.0.0.1:22 embedtunnel@grace.example    # then curl 127.0.0.1:9000: refused
```

## Test

`deploy/ssh-tunnel/test/run.sh` runs this README's `run:` blocks in two throwaway containers
(a client with systemd, a far end with `sshd`, OpenSSH 10.0 of Debian 13), then one check per
scenario of the spec, one PASS/FAIL line each; about 5 minutes, Docker needed, everything
removed at the end.
