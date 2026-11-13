#!/bin/bash
# Runs once in a new VM of this project, as the VM user with passwordless sudo, after
# devvm's packages are installed (see .devvm/config.env). Everything of the system
# itself runs in Docker images, so the VM is a Docker host and little else.
set -euo pipefail

# OpenSearch (warehouse) refuses to start on a Docker host below this
echo 'vm.max_map_count = 262144' | sudo tee /etc/sysctl.d/90-opensearch.conf > /dev/null
sudo sysctl -q --system

# uv and uvx, from Astral's installer into ~/.local/bin, which the default Debian
# profile adds to the PATH of login shells once the folder exists
curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
# The git hook of this repository (.pre-commit-config.yaml: ruff) runs through
# pre-commit; a uv tool install rather than uvx, since the hook that pre-commit writes
# points at a persistent interpreter. The Debian package is too old for the config.
~/.local/bin/uv tool install pre-commit

# The OpenSpec CLI, which the crawler's /opsx:* skills call (python/crawler/AGENTS.md);
# pinned to the version in use, into ~/.local, with its telemetry off for login shells
sudo apt-get install -y --no-install-recommends nodejs npm
npm install -g --prefix ~/.local @fission-ai/openspec@1.16.0
echo 'export OPENSPEC_TELEMETRY=0' >> ~/.profile

# The crawler's development setup (python/crawler/README.md, "Getting started"): the
# PostgreSQL server binaries without a running cluster (the tests start their own),
# update-mime-database, Python 3.14 from uv in ~/.venv (Debian 13 ships 3.13; the
# packages go in from the checkout, the README's install line) and the PATH to all three
sudo mkdir -p /etc/postgresql-common/createcluster.d
echo 'create_main_cluster = false' | sudo tee /etc/postgresql-common/createcluster.d/no-main-cluster.conf > /dev/null
sudo apt-get install -y --no-install-recommends postgresql-17 postgresql-client-17 shared-mime-info
~/.local/bin/uv venv --python 3.14 ~/.venv
echo 'export PATH="$HOME/.venv/bin:/usr/lib/postgresql/17/bin:$HOME/.local/bin:$PATH"' >> ~/.bashrc

# Seeing what a program does, which reviews and the crawler's benchmark use
# (python/crawler/benchmark/README.md, "Profiling"); perf needs sudo, since Debian sets
# kernel.perf_event_paranoid to 3. GitHub's CLI for the repository's issues and pull
# requests, mdBook for the guide (docs/guide/). The NFS benchmark's tools are opt-in:
# `devvm bench-setup` (.devvm/commands.sh)
sudo apt-get install -y --no-install-recommends strace linux-perf gh mdbook

# Rust for modama-rs and the crawl I/O playground (modama-rs/crawl-io-playground/):
# rustup into ~/.cargo, pinned to the toolchain in use, and a C linker
sudo apt-get install -y --no-install-recommends gcc libc6-dev
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain 1.99.1
