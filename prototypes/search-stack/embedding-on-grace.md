# Embedding on grace (prototype)

The warehouse's embedding moves to a service on grace (NVIDIA GH200), reached from the
staging host through an SSH tunnel. Status: being set up, 2026-11-13. Decided by @weber:
the warehouse calls an embeddings service (item 346, option A); a systemd service for the
prototype; the tunnel as a systemd unit with a dedicated `nologin` account and a
restricted key. The design is the OpenSpec change `embedding-service-grace` (in
`python/crawler/openspec/changes/`, being written); this page is the setup.

## Why

On grace, the GPU embeds 30 to 70 times more texts per second than grace's 72 CPU cores
(the benchmark in `perf/grace-embedding/`, quick run 2026-11-13: short texts 68,600
against 2,028 texts/s, mixed 25,300 against 412, long 7,800 against about 114). Its
vectors agree with production's (minimum cosine 0.99999). The comparison that decides is
staging's indexing before and after the switch: staging runs on an EPYC, not on grace's
CPU.

## How the pieces connect

```
staging host (ptycho)                                   grace
Celery workers (compose)                                 embeddings service
  EMBED_API_URL=http://host.docker.internal:17656/v1      127.0.0.1:7656
        |                                                        ^
        v                                                        |
  172.17.0.1:17656  --- systemd unit: ssh -N -L ----------> embedtunnel@grace (nologin)
  (Docker's bridge address)
```

- **The service** runs on grace, next to the GPU, and listens only on `127.0.0.1:7656`.
- **The tunnel** runs on the staging host, where the consumers are, as a systemd unit
  (the pattern of `deploy/beatepi/etc/systemd/system/er-c-data-smb.service`). It logs into
  a `nologin` account on grace whose key may only forward to `127.0.0.1:7656`.
- **The ports:** `7656` on grace, next to the crawler's 7654 (OAI-PMH) and browse's 7655;
  `17656` on the staging host, after staging's 1xxxx host ports (17654, 17655, 18081, ...).
- **A second forward, for chat:** grace's `127.0.0.1:11434` (Ollama's port, a language
  model running on grace) to `172.17.0.1:11434` on the staging host, in the same unit
  (@weber, 2026-11-13). AI Mode's chat could then use a local model instead of an external
  API; switching it over is a decision of its own, not part of this setup.
- **The containers** can't reach the staging host's `127.0.0.1`. The forward therefore
  listens on Docker's bridge address (usually `172.17.0.1`), as the beatepi unit binds to
  its bridge addresses, and the containers reach it as `host.docker.internal`
  (`extra_hosts: ["host.docker.internal:host-gateway"]` in compose).
- **The warehouse** already calls a remote embeddings service in OpenAI's format when
  `EMBED_API_URL` and `EMBED_API_KEY` are set (`src/transform/transform_core.py`,
  `src/utils/embedding_utils.py` `_embed`), and falls back to local embedding when it
  fails. One catch: that path cuts each text to its first 1,000 characters, while local
  embedding cuts at 512 tokens, so long records would embed differently. A patch in
  `patches/warehouse/` fixes that before the switch.

## Setup

### Check first

```bash
ss -ltn | grep -E ':7656\b|:17656\b'   # on grace and on the staging host: empty means free
ss -ltn | grep -E ':11434\b'           # on grace: the model's server listening; on the staging host: empty
ip -4 addr show docker0                # on the staging host: the bridge address, usually 172.17.0.1
```

### On grace: the tunnel's account

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin embedtunnel
sudo install -d -m 700 -o embedtunnel -g embedtunnel ~embedtunnel/.ssh
# ~embedtunnel/.ssh/authorized_keys (mode 600, owner embedtunnel), one line:
#   restrict,port-forwarding,permitopen="127.0.0.1:7656",permitopen="127.0.0.1:11434",command="/usr/sbin/nologin" ssh-ed25519 AAAA... staging-embed-tunnel
```

and in grace's `/etc/ssh/sshd_config`, at the end (then `sudo sshd -t && sudo systemctl reload ssh`):

```
Match User embedtunnel
    AllowTcpForwarding local
    AllowStreamLocalForwarding no
    PermitOpen 127.0.0.1:7656 127.0.0.1:11434
    PermitTTY no
    X11Forwarding no
```

`sudo sshd -T -C user=embedtunnel` shows what applies to the account: `allowtcpforwarding
local`, `allowstreamlocalforwarding no`, `permittty no`, `x11forwarding no` and the two
`permitopen` addresses. grace runs OpenSSH 9.6 (Ubuntu 24.04); the checks below were made
with 10.0, so try the refused cases once on grace too (change `embedding-service-grace`,
task 1.2).

What each part does (sshd(8), "AUTHORIZED_KEYS FILE FORMAT", and sshd_config(5); checked
on 2026-11-13 against OpenSSH 10.0's `sshd` with a throwaway server and a real client,
change `embedding-service-grace`, design D7):

- `restrict` turns off port, agent and X11 forwarding, PTY allocation and `~/.ssh/rc`;
  `port-forwarding` turns port forwarding on again.
- `permitopen` limits `ssh -L` to the address named, literally: no name lookup, so the
  unit's `-L` must say `127.0.0.1`, not `localhost` (a `localhost` forward was refused).
  It may be given more than once ("Multiple permitopen options may be applied separated
  by commas"); with both, both forwards worked and a third port was refused.
- `restrict` does **not** stop a command or a shell: with only the first three options and
  an account with a shell, `ssh … id -un` ran. The `nologin` shell stops it, and
  `command="/usr/sbin/nologin"` stops it even if the account's shell were changed by
  mistake. The unit's `-N` asks for no command, so the forced command never runs for it.
- `port-forwarding` turns remote forwards (`ssh -R`) on as well, and `permitopen` does not
  limit them: with the key line alone, `-R` opened a listener on the far end. Someone with
  the key could then listen on grace's `127.0.0.1:7656` while the service is down and
  receive the warehouse's requests, token included. The `Match` block allows local
  forwards only (`AllowTcpForwarding local`); with it, `-R` was refused. `permitlisten="none"`
  in the key line is not accepted (the key was rejected).
- With the key line alone, `-R` also created a Unix socket on the far end; `-L` to a Unix
  socket there and a terminal (`ssh -tt`) were refused. With the `Match` block, all three
  were refused. Its other lines (`AllowStreamLocalForwarding no`, `PermitOpen`,
  `PermitTTY no`, `X11Forwarding no`) changed no outcome on 10.0, but they hold on the
  server side whatever the key line says (review of the change, S5).

### On the staging host: the key and the unit

A key of its own, without a passphrase, readable only by root:

```bash
sudo install -d -m 700 /var/local/sshvpn
sudo ssh-keygen -t ed25519 -N '' -C staging-embed-tunnel -f /var/local/sshvpn/staging-embed-tunnel
# its .pub goes into embedtunnel's authorized_keys on grace (above)
```

`/etc/systemd/system/embed-tunnel.service` (replace `<grace>` with grace's host name):

```ini
[Unit]
Description=SSH tunnel to grace: 172.17.0.1:17656 -> 127.0.0.1:7656 (embedding), 172.17.0.1:11434 -> 127.0.0.1:11434 (chat model)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -o ConnectTimeout=10 -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -N -L 172.17.0.1:17656:127.0.0.1:7656 -L 172.17.0.1:11434:127.0.0.1:11434 -i /var/local/sshvpn/staging-embed-tunnel embedtunnel@<grace>
Restart=always
RestartSec=30s

[Install]
WantedBy=multi-user.target
```

`ConnectTimeout=10`: while grace is down, each attempt gives up after 10 s instead of about
2 minutes, then the 30 s pause.
`After=docker.service`: the bridge address exists only once Docker is up; until then
`ExitOnForwardFailure` makes the unit fail, and `Restart=always` tries again 30 s later.
Accept grace's host key once as root before enabling the unit (`sudo ssh -i
/var/local/sshvpn/staging-embed-tunnel embedtunnel@<grace>`, answer yes; the session ends
at once, as the account has no shell).

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now embed-tunnel.service
systemctl status embed-tunnel.service
journalctl -u embed-tunnel.service -f
```

### Test the tunnel before the service exists

```bash
# on grace, a stand-in that answers on the service's address (Ctrl-C to stop):
python3 -m http.server 7656 --bind 127.0.0.1

# on the staging host, from a container, as the warehouse's workers will reach it:
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -sI http://host.docker.internal:17656/
```

`HTTP/1.0 200 OK` means that the tunnel, the bind address and the staging host's firewall
are all right. The chat forward, with the model's server running on grace:

```bash
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -s http://host.docker.internal:11434/v1/models
```

It lists the models the server offers (Ollama answers OpenAI's `/v1/models`). No answer at all with the unit running usually means a firewall between
containers and the host; `curl -sI http://172.17.0.1:17656/` on the host itself tells the
two apart.

## Still to come

- **The service** on grace: a systemd service under its own user, from the benchmark's
  locked venv (`perf/grace-embedding/requirements-gpu.txt`, Python 3.12), so `nvidia-smi`
  and `nvtop` show it under that name; the token from a file outside the repository.
  Docker with NVIDIA's Container Toolkit is an option for a permanent service later.
- **The warehouse patch** (the 1,000-character cut) and the compose settings
  (`EMBED_API_URL`, `extra_hosts`, and the token in a file of its own, `embed.env`, which
  only `airflow-worker-transform` reads: in `keys.env` the search API would take it too and
  send it to EGI with every reranked search; change `embedding-service-grace`, design D11).
- **Measurements on staging**, before and after, with no harvest or indexing running:
  throughput, and which step becomes the bottleneck once embedding is offloaded.
- **A reusable template** of the tunnel unit and its README in `deploy/`, from this page.
- **A real network connection** instead of the tunnel.

## Before anything beyond the demo

Accepted for the demo (@weber, 349 and 350, 2026-11-13: "let's keep it for now, but make a
note to secure it properly. For now it is just a demo and not many people have access to
these systems"; "they can see the data anyway in the file system, so nothing new to
them"). The people with accounts on grace and the staging host can read the record texts
on the storage already. What securing it has to cover is what they cannot do today:

- **Forged vectors, through a freed port.** 7656 on grace and `172.17.0.1:17656` on the
  staging host are unprivileged. While the service or the tunnel is down, any local user
  could listen there, take the warehouse's requests with the token, and answer with
  vectors that go into the index. Fix: ports below 1024 at both ends.
- **Ollama's admin calls.** 11434 has no authentication: whoever holds the key, any user on
  the staging host and any container there can call `/api/delete`, `/api/pull` and
  `/api/create`, not only chat. Fix: a token or a proxy in front of it, and a privileged
  port at the staging end.

The details and the scenarios are in the change `embedding-service-grace` (proposal,
"Before anything beyond the demo"); the backlog item is "Secure the grace tunnel before
wider use".
