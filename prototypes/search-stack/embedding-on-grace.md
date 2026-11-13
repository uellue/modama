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
ip -4 addr show docker0                # on the staging host: the bridge address, usually 172.17.0.1
```

### On grace: the tunnel's account

```bash
sudo useradd --system --create-home --shell /usr/sbin/nologin embedtunnel
sudo install -d -m 700 -o embedtunnel -g embedtunnel ~embedtunnel/.ssh
# ~embedtunnel/.ssh/authorized_keys (mode 600, owner embedtunnel), one line:
#   restrict,port-forwarding,permitopen="127.0.0.1:7656" ssh-ed25519 AAAA... staging-embed-tunnel
```

`restrict` turns off everything (shell, agent and X11 forwarding, PTY), then
`port-forwarding` allows forwarding again, and `permitopen` limits it to the one address.
So the key opens nothing but this tunnel, even if the account's shell were changed by
mistake. The option names are written from memory; the change `embedding-service-grace`
checks them against sshd(8) and corrects this page.

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
Description=SSH tunnel: 172.17.0.1:17656 -> grace 127.0.0.1:7656 (embedding service)
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh -o ServerAliveInterval=60 -o ExitOnForwardFailure=yes -N -L 172.17.0.1:17656:127.0.0.1:7656 -i /var/local/sshvpn/staging-embed-tunnel embedtunnel@<grace>
Restart=always
RestartSec=30s

[Install]
WantedBy=multi-user.target
```

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
are all right. No answer at all with the unit running usually means a firewall between
containers and the host; `curl -sI http://172.17.0.1:17656/` on the host itself tells the
two apart.

## Still to come

- **The service** on grace: a systemd service under its own user, from the benchmark's
  locked venv (`perf/grace-embedding/requirements-gpu.txt`, Python 3.12), so `nvidia-smi`
  and `nvtop` show it under that name; the token from a file outside the repository.
  Docker with NVIDIA's Container Toolkit is an option for a permanent service later.
- **The warehouse patch** (the 1,000-character cut) and the compose settings
  (`EMBED_API_URL`, `EMBED_API_KEY` from the secrets, `extra_hosts`).
- **Measurements on staging**, before and after, with no harvest or indexing running:
  throughput, and which step becomes the bottleneck once embedding is offloaded.
- **A reusable template** of the tunnel unit and its README in `deploy/`, from this page.
- **A real network connection** instead of the tunnel.
