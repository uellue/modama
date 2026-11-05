#!/bin/bash
# One-shot setup of the warehouse, run by the warehouse-init service on every start;
# each step only does what is missing, so a running warehouse is left as it is:
#   databases datasetdb and filedb with upstream's schema, then alembic migrations;
#   the OpenSearch index; the crawler as the only active endpoint; the search API's
#   database and its own role; the read-only role of modama-chain.
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

# Our endpoint, the only active one; the search API's database and role; the read-only
# role of modama-chain. Values as query parameters or quoted literals, never pasted in.
python - <<'PY'
import os
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


def connect(dbname):
    return psycopg.connect(host="postgres", user=os.environ["POSTGRES_ADMIN"],
                           password=os.environ["POSTGRES_PASSWORD"], dbname=dbname, autocommit=True)


def env_file(path):
    return dict(line.split("=", 1) for line in open(path).read().splitlines()
                if line and not line.startswith("#"))


def role(conn, name, password):
    """Create the login role if missing, and set its password."""
    if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (name,)).fetchone():
        conn.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(name)))
    conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(sql.Identifier(name), sql.Literal(password)))


url, db = os.environ["ENDPOINT_URL"], os.environ["POSTGRES_DB"]
with connect(db) as conn:
    # One repository and endpoint of ours, found by its code, so that a changed URL moves it
    conn.execute(
        """INSERT INTO repositories (name, code, description, base_url, is_active)
           SELECT 'ER-C', 'ERC', 'modama crawler OAI-PMH endpoint', %s, true
           WHERE NOT EXISTS (SELECT FROM repositories WHERE code = 'ERC')""",
        (url.removesuffix("/oai"),),
    )
    (repository,) = conn.execute("SELECT id FROM repositories WHERE code = 'ERC'").fetchone()
    if conn.execute("SELECT 1 FROM endpoints WHERE repository_id = %s", (repository,)).fetchone():
        conn.execute("UPDATE endpoints SET harvest_url = %s, is_active = true WHERE repository_id = %s",
                     (url, repository))
    else:
        conn.execute(
            """INSERT INTO endpoints (repository_id, name, harvest_url, protocol, harvest_params,
                                      harvest_schedule, is_active)
               VALUES (%s, 'ER-C crawler', %s, 'OAI-PMH', '{"metadata_prefix": "oai_dc"}', INTERVAL '1 day', true)""",
            (repository, url),
        )
    # upstream's seed and migrations add endpoints of other repositories, active: a harvest
    # without harvest_urls (the UI's trigger, a HARVEST_SCHEDULE) would fetch them all
    off = conn.execute("UPDATE endpoints SET is_active = false WHERE repository_id <> %s AND is_active",
                       (repository,)).rowcount
    if off:
        print(f"deactivated {off} endpoints of other repositories")

    reader = conninfo_to_dict(os.environ["MODAMA_CHAIN_WAREHOUSE_DB"])
    role(conn, reader["user"], reader["password"])
    for statement in (
        "GRANT CONNECT ON DATABASE {db} TO {r}",
        "GRANT USAGE ON SCHEMA public TO {r}",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO {r}",
        "ALTER DEFAULT PRIVILEGES FOR ROLE {admin} IN SCHEMA public GRANT SELECT ON TABLES TO {r}",
    ):
        conn.execute(sql.SQL(statement).format(db=sql.Identifier(db), r=sql.Identifier(reader["user"]),
                                               admin=sql.Identifier(os.environ["POSTGRES_ADMIN"])))

search_api = env_file("/secrets/search-api-db.env")
with connect("postgres") as conn:
    role(conn, search_api["POSTGRES_USER"], search_api["POSTGRES_PASSWORD"])
    if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (search_api["POSTGRES_DB"],)).fetchone():
        conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
            sql.Identifier(search_api["POSTGRES_DB"]), sql.Identifier(search_api["POSTGRES_USER"])))
PY
echo "warehouse ready"
