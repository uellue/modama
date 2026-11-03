# AGENTS.md

Instructions for AI coding agents working in this repository. Claude Code reads this file through the one-line `CLAUDE.md` next to it; Codex reads it directly. Subprojects keep their own `AGENTS.md` (for example `python/crawler/AGENTS.md`).

See also `modama-rs/AGENTS.md` for the Rust workspace and the agent GUI.

## Wording

Before writing text that people read (UI strings, error and log messages,
docs, API descriptions), read `CONTEXT.md` and use its terms; don't use the
words it lists under _Avoid_. If a term is missing or doesn't fit, raise it
instead of inventing one.

## What this is

"modama" is the ER-C data management system: a set of Docker services (Nextcloud, WebDAV, SMB ingest, permissions, management interface, backup) plus clients. Most user-facing docs live in `README.md` and the mdBook guide in `docs/guide/src/`. The repo uses git submodules (`git submodule init && git submodule update`); submodule dirs (`deploy/wsgidav`, `deploy/tsm-client`, `deploy/gateway/acme.sh`, `python/PyInotify`, `prototypes/EOSC-Data-Commons/*`) are third-party/forked code, so don't edit them as part of normal changes.

Top-level layout:
- `python/` – Python services and clients: `mgmtinterface` (Flask management UI/API), `permissions`, `smbdrop-gui`, the `*-client` packages, `modama-common`, and `crawler` (see below).
- `modama-rs/` – Cargo workspace: `smbdrop` (SMB ingest share service), `modama-agent` (runs on lab/instrument PCs, mounts ingest shares), `modama-common`. Clippy denies `unwrap`/`expect` workspace-wide.
- `mgmtinterface-new/` – React/TypeScript (Vite) rewrite of the management interface.
- `deploy/` – Dockerfiles, `docker-compose.yml` + `docker-compose.override.yml` (test, the default) or `+ docker-compose.prod.yml` (prod), `build.sh`, `upprod.sh`/`downprod.sh`, `testconf/`/`prodconf/`. Test deployment data lives in `deploy/testfolder/` (`sudo ./preparefolders.sh`). Secrets are expected in `/var/local/data-mgmt/` outside the repo.
- `devvm/` – `devvm.sh` creates/manages a libvirt/KVM VM (Debian + Docker) for running the test deployment and Docker-based tests in isolation. Generic settings in `defaults.env`, site-specific ones in gitignored `site.env`.
- `prototypes/` – notebooks and experiments; excluded from ruff checks via pre-commit.

## Commands (mirrors `.gitlab-ci.yml`)

```bash
# Lint/format (Python, whole repo; config in ruff.toml)
uvx ruff format --check --diff
uvx ruff check
pre-commit install --install-hooks   # runs ruff on commit

# mgmtinterface tests (CI installs the three *-client packages first)
cd python/mgmtinterface && pytest tests

# Rust
cd modama-rs && cargo check && cargo clippy && cargo test
cargo llvm-cov --html                 # coverage

# mgmtinterface-new
cd mgmtinterface-new && npm ci && npm run lint && npm run build && npm test

# Docs
cd docs/guide && mdbook serve --port 9991
```

## Crawler (`python/crawler`, active on the `crawler` branch)

OAI-PMH server over the data file tree, backed by PostgreSQL (Python ≥ 3.14). The devcontainer in `.devcontainer/` is set up for this package. Commands, architecture, conventions and test fixtures are in `python/crawler/AGENTS.md`, which `python/crawler/CLAUDE.md` imports.
