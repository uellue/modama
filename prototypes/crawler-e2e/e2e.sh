#!/bin/bash
# End-to-end test of the crawler with the EOSC warehouse. Usage: ./e2e.sh setup | up | reset | test | down | clean
set -euo pipefail
cd "$(dirname "$0")"
WH=../EOSC-Data-Commons/metadata-warehouse
export PATH="$HOME/.local/bin:$PATH"
dc() { docker compose -f compose.yml "$@"; }
# environment of the warehouse scripts that run on the host (create_db.py, alembic)
host_env() { set -a; . ./warehouse.env; set +a; }

# the services of the test; frontend, coordinator, dashboards and pgadmin are only for looking around
SERVICES="postgres broker opensearch transform airflow-postgres airflow-init airflow-api-server airflow-scheduler \
  airflow-dag-processor airflow-worker airflow-worker-transform search-api crawler crawler-db"

case "${1:-}" in
setup)
    if [ ! -e warehouse.env ]; then
        fernet=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
        sed -e "s|@FERNET@|$fernet|" -e "s|@JWT@|$(openssl rand -hex 32)|" -e "s|@SECRET@|$(openssl rand -hex 32)|" \
            -e "s|^AIRFLOW_UID=.*|AIRFLOW_UID=$(id -u)|" warehouse.env.template > warehouse.env
    fi
    # keys.env is the env_file of the upstream compose and must exist; the override replaces its content
    [ -e "$WH/keys.env" ] || cp "$WH/keys.env.template" "$WH/keys.env"
    # the fastembed cache is a bind mount that the airflow user has to write to
    mkdir -p "$WH/cache/fastembed" 2>/dev/null || sudo mkdir -p "$WH/cache/fastembed"
    [ -w "$WH/cache/fastembed" ] || sudo chmod -R a+rwX "$WH/cache"
    dc config --quiet && echo "compose config ok"
    ;;
up)
    dc up -d --build --wait --wait-timeout 900 $SERVICES
    ;;
reset)
    host_env
    # warehouse databases and schema, as upstream's e2e does
    (cd "$WH/scripts/postgres_data" && uv run create_db.py --db datasetdb --reset && uv run create_db.py --db filedb --reset)
    # alembic/env.py still reads the old variable names
    (cd "$WH" && export POSTGRES_ADDRESS=127.0.0.1 POSTGRES_PORT=5432 POSTGRES_DB=datasetdb \
        && uv run alembic stamp 0001_baseline && uv run alembic upgrade head)
    dc exec -T postgres psql -v ON_ERROR_STOP=1 -U "$POSTGRES_ADMIN" -d datasetdb < endpoint.sql
    # database of the search API (users, conversations); it creates its tables on start
    dc exec -T postgres psql -U "$POSTGRES_ADMIN" -d datasetdb -tc "SELECT 1 FROM pg_database WHERE datname = 'appdb'" | grep -q 1 \
        || dc exec -T postgres psql -U "$POSTGRES_ADMIN" -d datasetdb -c "CREATE DATABASE appdb"
    curl -s -X DELETE "http://127.0.0.1:9200/$INDEX_NAME" >/dev/null || true
    # transform refuses to create the index itself
    (cd "$WH/scripts/opensearch_data" && uv run create_index.py)
    # crawler: empty database and data
    dc exec -T crawler-db psql -U postgres -c "DROP DATABASE IF EXISTS modama_crawler WITH (FORCE)" -d postgres
    dc exec -T crawler-db psql -U postgres -c "CREATE DATABASE modama_crawler" -d postgres
    dc restart crawler search-api
    dc exec -T crawler sh -c 'rm -rf /data/* /data/.[!.]* 2>/dev/null || true'
    ;;
test)
    dc exec -T crawler pytest -v -p no:cacheprovider /e2e/test_e2e.py "${@:2}"
    ;;
down)
    dc down
    ;;
clean)
    dc down -v
    ;;
*)
    sed -n 2p "$0"; exit 2
    ;;
esac
