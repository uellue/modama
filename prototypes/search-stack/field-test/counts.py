"""Read-only counts for the staging field test, run in the crawler container:
dc exec -T crawler python - < field-test/counts.py

The directories with the most records in the crawler, and how many records the
warehouse has for our endpoint so far (the harvest's progress)."""

import os

import psycopg

with psycopg.connect(
    os.environ.get(
        "MODAMA_CHAIN_CRAWLER_DB", "host=crawler-db dbname=modama_crawler user=postgres"
    )
) as c:
    print("crawler: records per directory, the largest ten")
    for n, d in c.execute(
        """SELECT count(*), regexp_replace(metadata->'identifier'->>0, '/[^/]*$', '') AS dir
           FROM records GROUP BY dir ORDER BY 1 DESC LIMIT 10"""
    ):
        print(f"{n:8}  {d}")

with psycopg.connect(os.environ["MODAMA_CHAIN_WAREHOUSE_DB"]) as c:
    (n,) = c.execute(
        """SELECT count(*) FROM records r JOIN endpoints e ON e.id = r.endpoint_id
           WHERE e.harvest_url = 'http://crawler:7654/oai'"""
    ).fetchone()
    print(f"warehouse: {n} records of our endpoint so far")
