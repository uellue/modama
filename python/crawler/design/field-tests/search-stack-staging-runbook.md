# Runbook: the search stack on real data (staging), 2026-11-10

Field test, one shot: @weber runs the search stack (`/prototypes/search-stack/`, as the
project `search-staging`) on the development server that hosts the devvm VM, on the real
data tree: first `adhoc/libertem` only, then the whole tree. The state it builds is kept
as the demo instance.

Goals (@weber):

- follow the development on real data;
- show colleagues what works and collect their feedback (they search through SSH port
  forwarding to the server's localhost);
- collect real-world issues as test cases, and fix them;
- a performance baseline on hot data over NFS: cache behaviour, latency and bandwidth, a
  tree far larger than RAM, kernel prefetching;
- on the way to merging the test deployment into `deploy/`.

## Safety

Agreed with @weber, co-admin of the server, 2026-11-10.

- **Reads:** the data tree, read-only (a `:ro` bind mount, enforced by Docker), as
  @weber's uid and groups (`user` and `group_add`, enforced by Docker; NFS squashes
  root). The index shows only what @weber may see; the developers with access to the
  server are trusted with it. No real secrets: the stack uses the throwaway test secrets
  of `testconf/secrets/` (accepted: ports on localhost, trusted users).
- **Writes:** Docker's images, volumes and build caches, as `docker compose up` does, and
  the checkout (shared with the VM). Never `/storage`. Untracked files in the checkout
  are never deleted.
- **Load:** native, no limits. It is a development server, and finding problematic
  behaviour before production is a goal; 24 cores to use. Disk use of `/` and Docker's
  root is watched (`monitor.sh` warns above 90 %).
- **Network:** ports on 127.0.0.1 only: 18000 search API, 18081 Airflow, 17654 crawler,
  19200 OpenSearch, 13000 matchmaker (since 2026-11-12). Colleagues reach them with SSH
  port forwarding. No external interfaces. matchmaker's server calls outside services
  for its FAIR check and Data Player, and its page EGI's Matomo unless opened as
  `localhost` (@weber, 2026-11-12).
- **Stop:** `./downstaging.sh`; a running crawl records itself as failed. Clean-up:
  `./downstaging.sh --reset` deletes the staging volumes, never the data tree.
- **Never:** a write to `/storage`; deleting or changing anyone's files outside this
  test; leaking secrets (SSH keys, tokens on the server); anything pushed or published
  with the server's credentials (agent forwarding, `gh`, `docker login`). The agent has
  no shell on the server: it reads the shared checkout only, and @weber runs every
  command.
- **Recording:** the terminal's output and timing, never keystrokes, go to
  `.claude/field-tests/run-<n>/` in the checkout (gitignored, private). The agent reads
  it as it goes, and it stays in the agent's transcript: keep secrets off the screen.
  Look through it before anything is shared.

## Settings

`staging.env` in `prototypes/search-stack/` (gitignored), written in steps 3 to 7:

```
MODAMA_SECRETS_DIR=./testconf/secrets   # the throwaway test secrets
STAGING_DATA=/storage/er-c-data         # the data tree, mounted whole at /data, so that
                                        # identifiers stay the same for the full crawl
STAGING_USER=<uid>:<gid>                # who the crawler reads the tree as
STAGING_GROUP=<gid of iff>              # the group some of the tree needs
STAGING_CRAWL_CONFIG=libertem.toml      # the crawl's exclusions in stagingconf/;
                                        # full.toml for the whole tree
AIRFLOW_TASK_LIMIT=16                   # at most 16 indexing batches at once on this shared
                                        # machine (@weber, 2026-11-12)
```

What each service then chooses on this machine, and how to change it: `./cpu-budget.sh staging`, and the stack's README, "CPU budget".

## Steps

On the server, as yourself, one line at a time.

**1.** Go to the stack's folder in the shared checkout:

```bash
cd ~/src/data-management-system/prototypes/search-stack
```

**2.** Start the recording (a copy of kaizen's `record.sh`) into the next `run-<n>`;
`exit` ends it:

```bash
FIELD_TEST_DIR=$HOME/src/data-management-system/.claude/field-tests bash ../../.claude/field-tests/record.sh
```

**2a.** In the recorded shell, check the channel: type a note at the prompt, and wait
until the agent has read it back from the recording before going on:

```bash
# probe
```

**3 to 7.** Write the settings:

```bash
echo "MODAMA_SECRETS_DIR=./testconf/secrets" > staging.env
echo "STAGING_DATA=/storage/er-c-data" >> staging.env
echo "STAGING_USER=$(id -u):$(id -g)" >> staging.env
echo "STAGING_GROUP=$(getent group iff | cut -d: -f3)" >> staging.env
echo "STAGING_CRAWL_CONFIG=libertem.toml" >> staging.env
echo "AIRFLOW_TASK_LIMIT=16" >> staging.env
```

**8.** Check what the stack will use, and that you can read the subtree:

```bash
cat staging.env; ls /storage/er-c-data/adhoc/libertem | head
```

**9.** Disk space before:

```bash
df -h / "$(docker info -f '{{.DockerRootDir}}')"
```

**10.** In a second terminal, in the same folder, start the monitor into the run's
folder (`<n>` from step 2):

```bash
./monitor.sh "$HOME/src/data-management-system/.claude/field-tests/run-<n>/monitor.log"
```

**11.** Build the images and start the stack. The timer crawls at once and starts the
harvest when the crawl is done:

```bash
./upstaging.sh --build
```

**12.** A shorthand for the commands below:

```bash
dc() { docker compose -p search-staging --env-file staging.env -f docker-compose.yml -f docker-compose.staging.yml "$@"; }
```

**13.** Follow the crawl until "harvest … started"; Ctrl-C leaves it running:

```bash
dc logs -f crawl-timer
```

**14.** Crawl, harvest, indexing, and the freshness time:

```bash
dc exec crawler modama-chain status
```

**15.** A first search:

```bash
curl -s 'http://127.0.0.1:18000/search?q=libertem&resource=datasets' | head -c 2000
```

**16.** One path through every stage (a path you know):

```bash
dc exec crawler modama-chain trace /adhoc/libertem/<path>
```

**17.** Stop, keeping the state:

```bash
./downstaging.sh
```

## The whole tree

Run 2, overnight, right after run 1 (@weber, 2026-11-10). The timer crawls at 19:00 UTC
with the configuration it was started with, then starts the harvest, which starts the
indexing: nothing has to stay attached. (A crawl started with `dc exec` would end with
the terminal.)

Switch the crawl's configuration to the whole tree; `./upstaging.sh` then recreates
only `crawl-timer`, whose command changed; the state stays:

```bash
sed -i 's/=libertem.toml/=full.toml/' staging.env
```
```bash
./upstaging.sh
```

Larger indexing batches (@weber, 2026-11-10; finding F9): 2,000 harvest events per task
instead of 250, and four batches at once (`docker-compose.staging.yml`); then
`./upstaging.sh` again (it restarts the Airflow services):

```bash
echo "CELERY_BATCH_SIZE=2000" >> staging.env
```

Check that the timer waits for 19:00 with the new configuration:

```bash
dc logs --tail 3 crawl-timer
```

Optional, for the performance baseline (F5), in a third terminal: the NFS counters of the
data tree's mount, into the run's folder:

```bash
../../.claude/field-tests/nfs-stats.sh "$HOME/src/data-management-system/.claude/field-tests/run-1/nfs.log"
```

Leave `monitor.sh` (and `nfs-stats.sh`) running overnight in a terminal that survives
the night (screen or tmux).

## For colleagues

```bash
ssh -N -L 13000:127.0.0.1:13000 -L 18000:127.0.0.1:18000 <you>@<server>
```

Then http://localhost:13000, the search's web frontend (matchmaker; added 2026-11-12,
started on its own with `dc pull matchmaker` and `dc up -d --no-deps matchmaker`; without
`--no-deps`, compose runs `warehouse-init` again), or
http://localhost:18000/search?q=…&resource=datasets. Open it as `localhost`: on any other
host name its page sends usage statistics to EGI's Matomo
(`/prototypes/search-stack/README.md`, "Open").

## Notes during the run

`#` lines at the prompt, or in `run-<n>/notes.md`.
