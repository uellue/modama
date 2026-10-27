FROM mcr.microsoft.com/devcontainers/python:3.14-trixie

# PostgreSQL server binaries: pytest-postgresql spawns throwaway clusters via
# pg_ctl, so we need the server installed, but no default cluster or service.
# shared-mime-info provides update-mime-database, used by pyxdg.
RUN mkdir -p /etc/postgresql-common/createcluster.d \
    && echo "create_main_cluster = false" > /etc/postgresql-common/createcluster.d/no-main-cluster.conf \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        xvfb xterm xdotool imagemagick xfonts-base \
        postgresql-17 \
        postgresql-client-17 \
        shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

ENV PATH=/usr/lib/postgresql/17/bin:$PATH
