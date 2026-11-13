# Tasks

Who runs what: coding agents write the code and run the tests in the VM; @weber (or grace's admins) runs everything on grace and staging, from commands in the READMEs and the runbook (agents have no shell there). The leans of design.md's open questions are assumed; a task that depends on one names it.

## 1. grace: what the service needs (@weber or grace's admins)

- [ ] 1.1 Read the full benchmark run (`.claude/field-tests/grace-results/`): the GPU's peak memory per worker at batch 256 for long texts, the float32 file's rate on the GPU; write the memory limit (Q9) and the float32 rate into design D3 and D5; verified by the two numbers in design.md with the result file named
- [ ] 1.2 The tunnel per `prototypes/search-stack/embedding-on-grace.md`, with the corrected key line and the `Match User embedtunnel` block (`AllowTcpForwarding local`) from this change; verified on grace by `sudo sshd -T -C user=embedtunnel | grep -iE 'allowtcpforwarding|disableforwarding'` showing `local` and `no`, and from the staging host by `ssh -i /var/local/sshvpn/staging-embed-tunnel embedtunnel@<grace> id` answering `This account is currently not available.` and `ssh -N -R 127.0.0.1:47656:127.0.0.1:22 …` failing with `remote port forwarding failed`
- [ ] 1.3 The page's stand-in test (`python3 -m http.server 7656 --bind 127.0.0.1` on grace, `curl` from a container on the staging host); verified by `HTTP/1.0 200 OK`
- [ ] 1.4 Create the service's account `modama-embed` (Q12; `useradd --system --create-home --shell /usr/sbin/nologin modama-embed`); verified by `getent passwd modama-embed` showing `/usr/sbin/nologin`

## 2. The service (`prototypes/search-stack/embedding-service/`)

- [ ] 2.1 `requirements-gpu.in` from the benchmark's plus FastAPI and uvicorn (releases at least two weeks old, looked up then; flagged in the hand-over), its lock file for Python 3.12 aarch64 with hashes (the benchmark's `uv pip compile` line), and a CPU lock for the tests in the VM; verified by `uv pip compile` reproducing both files and `pip install --require-hashes` succeeding in a fresh venv
- [ ] 2.2 Measure on grace, before writing the server, the float32 file on the GPU with `use_tf32` 0 against the local path's file on the CPU (a `bench.py` case or a short script beside it, the 512 texts of each set); verified by the minimum cosine per set in the hand-over: at least 0.99999 confirms D3/D4, below it goes to @weber (Q2) before 2.3
- [ ] 2.3 `server.py`: `POST /v1/embeddings`, `GET /health`, the token from `$CREDENTIALS_DIRECTORY/token`, the model check, sorting and sub-batches of 256, one GPU batch per worker at a time, 503 on the GPU's out-of-memory, one log line per request without text; verified by `test_server.py`, one test per scenario of the spec's service requirements (three texts, reverse order, 2,000 tokens, the first 512 tokens, no token, wrong token, another model, health, marker not logged, the memory limit with a tiny limit), run with the CPU provider in the VM
- [ ] 2.4 `modama-embed.service` (`User=modama-embed`, `LoadCredential=token:/etc/modama-embed/token`, `Restart=always`, `RestartSec=30s`, `--host 127.0.0.1 --workers 2`) and `README.md` (venv from the lock, the model files at the pinned revision and the float32 file, the token, install, enable, logs, how others on grace see it, how to stop it safely); verified by @weber on grace: `systemctl status modama-embed`, `curl -s 127.0.0.1:<port>/health` naming `CUDAExecutionProvider`, the scenarios "From another host" and "The process is killed", and `nvidia-smi` showing the processes under `modama-embed`

## 3. The check instrument (`embedding-service/check.py`)

- [ ] 3.1 Smoke test first: one fixed short text sent to a service and embedded locally, the cosine printed; verified by running it in the VM against `server.py` on the CPU provider
- [ ] 3.2 Then the rest: the benchmark's fixed short, mixed and long sets (`gen_texts.py`, by seed) plus over-length texts, minimum cosine and largest component difference per set against the local path's file (`EMBEDDING_MODEL_PATH` when `embedding-fp32-model` is in place), texts/s and MB/s at 1, 4 and 16 concurrent requests, exit status 1 below the bound; verified in the VM against `server.py`, and by a run with a deliberately wrong model file (the benchmark's int8) that exits 1 and names the set
- [ ] 3.3 Documented in the service's README with the command for staging (`docker compose exec airflow-worker-transform …`, the token from the environment, never on the command line); verified by running the documented command as written in the VM's test deployment against a service on the CPU provider (with the main session's OK for the stack)

## 4. The tunnel template (`deploy/ssh-tunnel/`)

- [ ] 4.1 `ssh-tunnel@.service` as in design D7, derived from the setup page's `embed-tunnel.service` and beatepi's unit; verified by `systemd-analyze verify` of an instance and a test that starts it in a throwaway systemd container against a throwaway `sshd` (keys made in a temporary folder; the way of design D7's check), with the forward answering
- [ ] 4.2 Tests of the spec's `ssh-tunnel` scenarios against that `sshd` with real `ssh` clients: unknown host key, port taken (exit, restart after 30 s), far end gone and back, a shell, a shell after the account's shell changed, two permitted destinations, another destination, `localhost` for `127.0.0.1`, a remote forward; verified by one test per scenario passing
- [ ] 4.3 `README.md`: the far end's account with `nologin`, the key (made on the client, never copied), the known-hosts line, the key line `restrict,port-forwarding,permitopen="HOST:PORT"[,permitopen=…],command="/usr/sbin/nologin"` and the `Match User` block with what each part does (design D7's table) and the optional `from=` (Q10), install, enable, logs, drop-ins for ports below 1024 and for `After=docker.service`; the setup page then points to it for the general part; verified by following it as written in the test of 4.1
- [ ] 4.4 The grace tunnel as an instance example (`embed.conf`) in the README; verified by the test of 4.1 using it with the placeholders filled
- [ ] 4.5 When @weber sends the version he runs on other hosts: compare it with the template and take over what it does better, or note why not; verified by the comparison in the hand-over

## 5. The warehouse side

- [ ] 5.1 `patches/warehouse/0005-embedding-service.patch`, against v1.10.0 with 0001 to 0004 applied (with 0001 to 0003 while `embedding-fp32-model` is not merged; the number then stays): `max_chars=None` sends texts whole, a 400 `context length` raises at once, a timeout of 30 s (Q8), `lazy_load=True` for the local model (Q7); a header in the conventions of 0001 to 0003; verified by `patch -p1 --dry-run` in the order of `warehouse-airflow.Dockerfile` and by tests in the transform venv against `server.py` on the CPU provider: a 5,000-character text arrives whole, the fallback within 10 s when nothing listens, within 3 minutes when the server never answers, on a wrong token, no request with an empty URL
- [ ] 5.2 `docker-compose.yml`: `airflow-worker-transform` takes `EMBED_API_URL: ${EMBED_API_URL:-}` and `extra_hosts: ["host.docker.internal:host-gateway"]` (the setup page); the `transform` service stays at `""`; verified by `docker compose config` showing the empty default and, with a test env file, `http://host.docker.internal:17656/v1`
- [ ] 5.3 `field-test/batch-times.sh`: per batch, `service`, `fallback` or `local`, from upstream's lines (`embedding_utils.py:213,215,218`), and the count of fallbacks; verified against a log with one batch of each kind, made by the tests of 5.1
- [ ] 5.4 On staging (@weber, runbook steps): the secrets folder outside the checkout and `MODAMA_SECRETS_DIR` pointing at it, `EMBED_API_KEY` in its `keys.env`, `EMBED_API_URL=http://host.docker.internal:17656/v1` in `staging.env`; verified by `curl -s http://host.docker.internal:17656/health` from inside `airflow-worker-transform`, `grep -c '^EMBED_API_KEY=.'` on the new `keys.env` giving 1, and `git status` in the checkout showing no change under `testconf/secrets/`

## 6. Documentation in the repository

- [ ] 6.1 The stack's README: a section on the embedding service (what runs where, the switch, the way back, the token's place), `check.py` in "Measurements", `batch-times.sh`'s new column; verified by the commands in it run as written in the VM where they can run there
- [ ] 6.2 The staging runbook: the switch, the measurement (design D9) and the way back as numbered commands; verified by @weber running them in step 7
- [ ] 6.3 `python/crawler/BACKLOG.md`: the GPU item updated (this change; Docker later; query embedding later; TEI to re-evaluate), and a decision-log row in `design/architecture.md` for item 346 and the systemd decision, once accepted; verified by the diff

## 7. The prototype on staging (@weber, with the agent reading the recording)

- [ ] 7.1 The measurement of design D9, steps 1 to 6; verified by the records/s, per-batch, per-step, GPU, MB/s, fallback and vector numbers written as a finding in `design/field-tests/search-stack-staging-findings.md`
- [ ] 7.2 The bottleneck after the switch named from 7.1's per-step table, with a backlog item for it; verified by the item in `BACKLOG.md` citing the finding

## 8. Review

- [ ] 8.1 A review by an agent that did not write the code, given the code, this change's specs and design, not the author's conclusions (`design/review.md`); findings verified before acting; verified by the review's file next to this change and the fixes' commits
- [ ] 8.2 `uvx pre-commit run --all-files` from the repository's root after `git add` of new files; verified by its output, and the skipped tests counted

## Workflow follow-up

- Archive the change after @weber accepts the prototype's results.
