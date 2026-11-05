#!/bin/bash
# One-shot setup of the warehouse, run by the warehouse-init service on every start;
# each step only does what is missing, so a running warehouse is left as it is:
#   databases datasetdb and filedb with upstream's schema, then alembic migrations;
#   the OpenSearch index; the crawler as an endpoint to harvest; the search API's
#   database appdb; the read-only role chain_reader of modama-chain.
set -euo pipefail
cd /warehouse
export PGPASSWORD=$POSTGRES_PASSWORD
sql() {  # database, statement; no psql in the image, so psycopg
    python -c '
import os, sys, psycopg
with psycopg.connect(host="postgres", user=os.environ["POSTGRES_ADMIN"], password=os.environ["POSTGRES_PASSWORD"], dbname=sys.argv[1], autocommit=True) as c:
    r = c.execute(sys.argv[2])
    if r.description: print(*(row[0] for row in r.fetchall()), sep="\n")
' "$@"
}

# A database without tables is set up with upstream's SQL. The postgres image creates
# datasetdb itself (POSTGRES_DB), empty, and create_db.py skips an existing database
# unless --reset, which resets only the schema; with no tables there is nothing to lose.
for db in "$POSTGRES_DB" "$FILE_DB"; do
    tables=0
    if [ -n "$(sql postgres "SELECT 1 FROM pg_database WHERE datname = '$db'")" ]; then
        tables=$(sql "$db" "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
    fi
    if [ "$tables" = 0 ]; then
        (cd scripts/postgres_data && python create_db.py --db "$db" --reset)
    fi
done
# create_db.py creates the baseline schema; alembic takes over from there
if [ -z "$(sql "$POSTGRES_DB" "SELECT 1 WHERE to_regclass('alembic_version') IS NOT NULL")" ]; then
    alembic stamp 0001_baseline
fi
alembic upgrade head

index_exists() {
    python - <<'PY'
import os
from opensearchpy import OpenSearch
client = OpenSearch(hosts=[{"host": os.environ["OPENSEARCH_ADDRESS_HOST"], "port": int(os.environ["OPENSEARCH_PORT_HOST"])}])
raise SystemExit(0 if client.indices.exists(index=os.environ["INDEX_NAME"]) else 1)
PY
}
# create_index.py reads ../../config/ relative to its folder, deletes any index of that
# name first, and only prints its errors: so only when missing, and checked afterwards
if ! index_exists; then
    (cd scripts/opensearch_data && python create_index.py)
    index_exists || { echo "index $INDEX_NAME was not created" >&2; exit 1; }
fi

sql "$POSTGRES_DB" "
INSERT INTO repositories (name, code, description, base_url, is_active)
SELECT 'ER-C', 'ERC', 'modama crawler OAI-PMH endpoint', '${ENDPOINT_URL%/oai}', true
WHERE NOT EXISTS (SELECT FROM repositories WHERE code = 'ERC');
INSERT INTO endpoints (repository_id, name, harvest_url, protocol, harvest_params, harvest_schedule, is_active)
SELECT id, 'ER-C crawler', '$ENDPOINT_URL', 'OAI-PMH', '{\"metadata_prefix\": \"oai_dc\"}'::jsonb, INTERVAL '1 day', true
FROM repositories WHERE code = 'ERC' AND NOT EXISTS (SELECT FROM endpoints WHERE harvest_url = '$ENDPOINT_URL');"

[ -n "$(sql postgres "SELECT 1 FROM pg_database WHERE datname = 'appdb'")" ] || sql postgres "CREATE DATABASE appdb"

reader_password=${MODAMA_CHAIN_WAREHOUSE_DB##*password=}
sql "$POSTGRES_DB" "
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'chain_reader') THEN CREATE ROLE chain_reader LOGIN; END IF;
END \$\$;
ALTER ROLE chain_reader PASSWORD '$reader_password';
GRANT CONNECT ON DATABASE $POSTGRES_DB TO chain_reader;
GRANT USAGE ON SCHEMA public TO chain_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO chain_reader;
ALTER DEFAULT PRIVILEGES FOR ROLE $POSTGRES_ADMIN IN SCHEMA public GRANT SELECT ON TABLES TO chain_reader;"
echo "warehouse ready"
