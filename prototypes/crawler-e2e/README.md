# Crawler end-to-end test

modama crawler (OAI-PMH) → EOSC harvester (inside the warehouse's Airflow) → metadata warehouse → OpenSearch → search API.

One compose project: the unmodified upstream compose of `../EOSC-Data-Commons/metadata-warehouse` (checked out at `v1.10.0`; the compose file is the source of truth, re-verify this setup on every upgrade), settings overridden in `warehouse.e2e.yml` and `warehouse.env`, plus our `crawler` and `crawler-db`. Needs Docker with compose ≥ 2.24 and `uv` (for the warehouse's own DB scripts); builds and pulls need network access (images, GitHub, Hugging Face for the embedding model).

```bash
./e2e.sh setup   # once: generates warehouse.env (gitignored) with fresh secrets
./e2e.sh up      # build and start; the first run takes a while
./e2e.sh reset   # empty warehouse DB, index and crawler; registers http://crawler:7654/oai as the only endpoint to harvest
./e2e.sh test    # pytest inside the crawler container
./e2e.sh down    # or clean, which also removes the volumes
```

The test builds a tree in the crawler container from the crawler's own fixture generators (EMPAD pair, Zarr, a corrupt Zarr store, a venv, the core collection's mixed files, plain text files), crawls it, triggers the Airflow DAG `warehouse_harvest_and_index` for our endpoint only, and checks, in this order: the harvest run is closed and has as many harvest events as `modama-crawler records` lists, none with an error, OpenSearch holds the same number, and `/search?q=ferritin` returns the right file. Then it adds a file, crawls and harvests again: the second run is incremental (`from_date` set) and brings exactly the new record. About 2.5 minutes.

For looking around by hand: the crawler on http://127.0.0.1:7654/oai, Airflow on :8081 (airflow/airflow), search API on :8000, OpenSearch on :9200. The frontend, dashboards and pgadmin are not started by `up`; `docker compose -f compose.yml up -d frontend` starts the frontend on :3000 (search works without `coordinator`; other functions may need it, unverified).

All ports are published on 127.0.0.1 only. To use them from a laptop's browser when the stack runs in a devvm VM behind a host (the VM's address on the libvirt network: `hostname -I` inside the VM), tunnel through the host:

```bash
ssh -N -J <you>@<host> -L 3000:127.0.0.1:3000 -L 8000:127.0.0.1:8000 -L 8081:127.0.0.1:8081 dev@<vm-ip>
```

Then open http://localhost:3000 (frontend; search for "ferritin"), http://localhost:8000/search?q=ferritin&resource=datasets (search API) or http://localhost:8081 (Airflow). Ctrl-C closes the tunnel.
