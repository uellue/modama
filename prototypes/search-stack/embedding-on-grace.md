# Embedding on grace (prototype)

The warehouse's embedding moves to a service on grace (NVIDIA GH200), reached from the
staging host through an SSH tunnel. Status: being set up, 2026-11-13. Decided by @weber:
the warehouse calls an embeddings service (item 346, option A); a systemd service for the
prototype; the tunnel as a systemd unit with a dedicated `nologin` account and a
restricted key. The design is the OpenSpec change `embedding-service-grace` (in
`python/crawler/openspec/changes/`); this page is the setup, and its "Runbook" the steps on
grace and staging, in order.

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

The general part, for this and any further tunnel, is `deploy/ssh-tunnel/README.md`: the
template unit `ssh-tunnel@.service` (its own account `ssh-tunnel` instead of root, the host
key pinned against the fingerprint read on the far end, no `ssh_config`), the far end's
account, the key line and the `Match` block, and a test of every refused case
(`deploy/ssh-tunnel/test/run.sh`). The unit below stays as it is until @weber moves it to
`ssh-tunnel@embed` (change `embedding-service-grace`, Q15).

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

## In the repository

- **The service:** `embedding-service/` (its README: what it answers, install, the unit
  `modama-embed.service`, `measure.py`, `check.py`, the tests). Docker with NVIDIA's
  Container Toolkit is an option for a permanent service later.
- **The warehouse patch** `patches/warehouse/0005-embedding-service.patch`: texts whole (the
  service cuts at 512 tokens as the local path does), 30 s per wait, no retry of a refused
  request, the local model loaded only when needed.
- **The compose settings:** the token in `embed.env` of the secrets folder, read by
  `airflow-worker-transform` only (in `keys.env` the search API would take it too and send it
  to EGI with every reranked search; design D11); `search-api` gets `EMBED_API_KEY: ""`;
  the worker takes `EMBED_API_URL` from the deployment's env file and reaches the host as
  `host.docker.internal`. `./runtest.sh` checks where the token goes.
- **`field-test/batch-times.sh`** says per batch `service`, `fallback` or `local`.
- **The tunnel template** `deploy/ssh-tunnel/`.
- Later: **a real network connection** instead of the tunnel.

## Runbook

The steps on grace and on the staging host, in order (change `embedding-service-grace`,
tasks 1 to 7; agents have no shell there). "root" marks a step that needs root. Each says
what to expect and how to undo it. Grace's GPU must be free of the benchmark first.
`<grace>` is grace's host name; on the staging host, `dc` is the staging runbook's
shorthand, run in `prototypes/search-stack/` of the checkout.

**1. On grace, root: the tunnel's far end as this page has it** (task 1.2). If set up
before this change, check that `authorized_keys` and `sshd_config` have the lines above.

```bash
sudo sshd -T -C user=embedtunnel | grep -E '^(allowtcpforwarding|allowstreamlocalforwarding|permittty|x11forwarding|permitopen) '
```

Expect `allowtcpforwarding local`, `allowstreamlocalforwarding no`, `permittty no`,
`x11forwarding no`, `permitopen 127.0.0.1:7656 127.0.0.1:11434`. grace runs OpenSSH 9.6,
the tests ran 10.0. Undo: remove the `Match` block, `sudo sshd -t && sudo systemctl reload ssh`.

**2. On the staging host, root: the refused cases, by hand** (task 1.2), with the tunnel's key:

```bash
k="-i /var/local/sshvpn/staging-embed-tunnel -o BatchMode=yes"
sudo ssh $k embedtunnel@<grace> id -un                  # This account is currently not available.
sudo ssh $k -tt embedtunnel@<grace> < /dev/null         # PTY allocation request failed
sudo timeout 15 ssh $k -o ExitOnForwardFailure=yes -N -R 127.0.0.1:47656:127.0.0.1:22 embedtunnel@<grace>   # remote port forwarding failed
sudo timeout 15 ssh $k -o ExitOnForwardFailure=yes -N -R /tmp/x.socket:127.0.0.1:22 embedtunnel@<grace>    # remote port forwarding failed
sudo timeout 10 ssh $k -N -L 127.0.0.1:47657:127.0.0.1:22 embedtunnel@<grace> & sleep 3; curl -s -m 3 127.0.0.1:47657; echo "curl exit $?"   # not 0: refused
sudo timeout 10 ssh $k -N -L 127.0.0.1:47658:/run/systemd/notify embedtunnel@<grace> & sleep 3; curl -s -m 3 127.0.0.1:47658; echo "curl exit $?"   # not 0: refused
```

Nothing to undo.

**3. On grace and the staging host: the stand-in test** of "Test the tunnel before the
service exists" above (task 1.3). Expect `HTTP/1.0 200 OK`. Stop the stand-in with Ctrl-C.

**4. On grace, root: the service's account, venv and model files** (tasks 1.4, 2.1):
`embedding-service/README.md`, "Install on grace", the blocks "The venv" and "The account,
the service's file and the model files". Expect `getent passwd modama-embed` to end in
`/usr/sbin/nologin`, the provider check to list `CUDAExecutionProvider`, `fetch` to print
the snapshot's folder. A pip error "THESE PACKAGES DO NOT MATCH THE HASHES": stop and report.
Undo: `sudo rm -r /opt/modama-embed && sudo userdel -r modama-embed`.

**5. On grace, as yourself, with the GPU free: the measurements** (tasks 1.1, 2.2):
`embedding-service/README.md`, "The memory limit" (`measure.py`, about 5 minutes). Send the
whole output back: per file and set, TF32 off and on against grace's CPU (minimum cosine,
largest component difference), and the GPU memory of one worker. Also the full benchmark
run's files into `.claude/field-tests/grace-results/`. Nothing to undo.

**6. On grace, root: the token, the unit, the limit; start** (task 2.4): the README's block
"The token, the unit and the limit", with `limit` twice the memory of step 5 in bytes.
Expect, after about 20 s:

```bash
systemctl status --no-pager modama-embed             # active (running)
curl -s 127.0.0.1:7656/health; echo                  # ... "provider":"CUDAExecutionProvider"
ss -ltn | grep 7656                                  # 127.0.0.1:7656 only
nvidia-smi                                           # two processes /opt/modama-embed/venv/bin/python, user modama-embed
journalctl -u modama-embed -n 5 --no-pager           # "worker ... ready", the limit, the other processes on the GPU
```

Undo: `sudo systemctl disable --now modama-embed` (the rest of step 4's undo removes the files).

**7. On grace, root: the scenarios that need grace** (task 2.4; spec `embedding-service`):

```bash
# The process is killed: back within a minute (30 s pause, then the model loads)
sudo kill -9 "$(systemctl show -p MainPID --value modama-embed)"; sleep 45; curl -s 127.0.0.1:7656/health; echo
# A limit too small for a batch: 503, then 200 for a small one; then the limit back
sudo mkdir -p /etc/systemd/system/modama-embed.service.d
printf '[Service]\nEnvironment=MODAMA_EMBED_MEM_LIMIT=50000000\n' | sudo tee /etc/systemd/system/modama-embed.service.d/tiny.conf
sudo systemctl daemon-reload && sudo systemctl restart modama-embed && sleep 20
python3 -c 'import json; print(json.dumps({"model": "bge-small-en-v1.5", "input": ["beam dose tilt " * 300] * 256}))' > /tmp/long.json
python3 -c 'import json; print(json.dumps({"model": "bge-small-en-v1.5", "input": ["ferritin"]}))' > /tmp/short.json
t=$(sudo cat /etc/modama-embed/token)
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $t" -H 'Content-Type: application/json' -d @/tmp/long.json 127.0.0.1:7656/v1/embeddings    # 503
curl -s -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $t" -H 'Content-Type: application/json' -d @/tmp/short.json 127.0.0.1:7656/v1/embeddings   # 200
unset t; rm /tmp/long.json /tmp/short.json
sudo rm /etc/systemd/system/modama-embed.service.d/tiny.conf && sudo systemctl daemon-reload && sudo systemctl restart modama-embed
```

If the tiny limit gives 500 instead of 503, send `journalctl -u modama-embed -n 30`: the
error's text tells the service which errors are out of memory (tested on the CPU only).
From another host (the staging host): `curl -m 5 http://<grace>:7656/health` must fail.

**8. On the staging host: the service through the tunnel** (task 2.4):

```bash
docker run --rm --add-host=host.docker.internal:host-gateway curlimages/curl -s http://host.docker.internal:17656/health
```

Expect the same answer as on grace. Nothing to undo.

**9. On the staging host: the secrets folder and the token** (task 5.4). First where
`MODAMA_SECRETS_DIR` points:

```bash
grep '^MODAMA_SECRETS_DIR=' staging.env
```

Only if it says `./testconf/secrets`: a folder outside the checkout (the token must never
land in `testconf/secrets/`, where `git status` would show it), and point there:

```bash
mkdir -p ~/.config/modama && cp -r testconf/secrets ~/.config/modama/staging-secrets && chmod 700 ~/.config/modama/staging-secrets
# then, in staging.env with an editor: MODAMA_SECRETS_DIR=<your home>/.config/modama/staging-secrets
```

Then in that folder's `embed.env`, with an editor, `EMBED_API_KEY=<the token>` (from `sudo
cat /etc/modama-embed/token` on grace, not in a recorded terminal), and check without
printing it:

```bash
grep -c '^EMBED_API_KEY=.' "$(sed -n 's/^MODAMA_SECRETS_DIR=//p' staging.env)/embed.env"   # 1
git status --short testconf/secrets/                                                      # nothing
```

Undo: `EMBED_API_KEY=` (empty) in that file.

**10. On the staging host: the measurement before the switch** (task 7.1; design D9, steps
1 to 3). Quiet first: `dc exec crawler modama-chain status` shows no crawl, harvest or
indexing running, and the next crawl (19:00 UTC) hours away. Then:

```bash
mkdir -p ~/embed-check
dc exec -T airflow-worker-transform bash < field-test/batch-times.sh > ~/embed-check/before-batch-times.txt
bash field-test/index-tasks.sh > ~/embed-check/before-index-tasks.csv
```

If the last indexing run's task logs are gone or are not of the current image: a re-index of
the last full harvest run, 30 minutes, with the probes, then stopped in Airflow's UI (the run,
"Mark as failed"):

```bash
dc exec airflow-api-server airflow dags trigger warehouse_transform_index -c '{"harvest_run_id": "<the harvest run>", "reuse_embeddings": false}'
dc exec -T airflow-worker-transform python3 - < field-test/indexing-probe.py > ~/embed-check/before-probe.log 2>&1 &
./monitor.sh ~/embed-check/before-monitor.log &
```

The per-step times on one batch of 2,000 (the header of `perf/phase-timer.py` has the
commands; with `-e EMBED_API_URL=` so that it embeds locally):

```bash
dc exec -T airflow-worker-transform sh -c 'cat > /tmp/phase-timer.py' < perf/phase-timer.py
dc exec -T -e EMBED_API_URL= -w /opt/airflow/project airflow-worker-transform /opt/airflow/transform-venv/bin/python /tmp/phase-timer.py 2000 > ~/embed-check/before-phases.txt
```

The snapshot of 1,000 stored vectors, before the re-index overwrites them:

```bash
dc exec -T crawler python - snapshot < embedding-service/check.py > ~/embed-check/before.jsonl   # "1000 records"
```

**11. On the staging host: the switch** (task 5.4; design D9, step 4):

```bash
echo 'EMBED_API_URL=http://host.docker.internal:17656/v1' >> staging.env
dc up -d airflow-worker-transform                       # ends the batches it runs; Airflow retries them
dc exec airflow-worker-transform curl -s http://host.docker.internal:17656/health; echo
dc exec search-api printenv EMBED_API_KEY               # an empty line
dc exec airflow-worker-transform sh -c 'test -n "$EMBED_API_KEY" && echo set'   # set
chk() { dc run --rm --no-deps -T -v "$PWD:/stack:ro" --entrypoint /opt/airflow/transform-venv/bin/python airflow-worker-transform /stack/embedding-service/check.py "$@"; }
chk sets > ~/embed-check/sets.txt; echo "exit $?"     # exit 0: every set within design D4
chk rate > ~/embed-check/rate.txt                       # texts/s and MB/s through the tunnel
```

If `chk sets` exits 1, switch back (below) and wait for @weber (design D4, Q2).

**12. On the staging host and grace: the measurement after** (task 7.1; design D9, steps 5
and 6): the same re-index as in step 10, let it finish, with the same probes into
`after-*` files, and on grace `nvidia-smi dmon -s um > ~/embed-dmon.log` meanwhile. During
it, the outage on purpose: `sudo systemctl stop embed-tunnel` for 10 minutes, then `sudo
systemctl start embed-tunnel`; batches fall back and none fails. Then:

```bash
dc exec -T airflow-worker-transform bash < field-test/batch-times.sh > ~/embed-check/after-batch-times.txt   # the last line counts service, fallback, local
bash field-test/index-tasks.sh > ~/embed-check/after-index-tasks.csv
dc exec -T -w /opt/airflow/project airflow-worker-transform /opt/airflow/transform-venv/bin/python /tmp/phase-timer.py 2000 > ~/embed-check/after-phases.txt
```

**13. On the staging host: the stored vectors** (design D9, step 7):

```bash
dc exec -T crawler python - snapshot < embedding-service/check.py > ~/embed-check/after.jsonl
dc run --rm --no-deps -T -v "$PWD:/stack:ro" -v ~/embed-check:/check:ro --entrypoint /opt/airflow/transform-venv/bin/python \
    airflow-worker-transform /stack/embedding-service/check.py compare /check/before.jsonl /check/after.jsonl
```

Expect exit 0 and the number of records compared. Send `~/embed-check/` back (it holds no
token; `before.jsonl` and `after.jsonl` hold record identifiers and vectors).

**The way back, at any time** (staging host): `EMBED_API_URL=` (empty) in `staging.env`,
then `dc up -d airflow-worker-transform`; the next batches embed locally and
`batch-times.sh` shows them as `local`. Vectors already indexed from the service stay; they
agree within design D4. The tunnel and the service may stay or go: `sudo systemctl disable
--now embed-tunnel` on the staging host (it also carries the chat model's forward), `sudo
systemctl disable --now modama-embed` on grace.

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
