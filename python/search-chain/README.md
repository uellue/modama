# modama-chain

Follows one path of the modama data tree through every stage of the search chain and says where it went missing:

tree → crawler (`modama-crawler`) → OAI-PMH → harvest (EOSC harvester in the warehouse's Airflow) → warehouse records → OpenSearch → search API

It only reads: no writes to any store, no triggers.

```bash
modama-chain trace /notes/readme.txt   # one line per stage; exit 0 consistent, 1 a stage diverges, 2 a store unreachable
modama-chain status                    # last crawl, harvest and indexing run, and the freshness time T
```

Written for the search stack (`/prototypes/search-stack/`), where it is installed in the crawler container:
`docker compose exec crawler modama-chain trace /notes/readme.txt`.

## Output

`trace` prints the path, then the keys the stages hold its dataset under (once, as a header), then one line per stage: stage, state, time and detail, with long details continued on indented lines. The keys: the path in the tree, the OAI identifier in the crawler and OAI-PMH, the identifier after its last `:` in the harvest, `<endpoint uuid>::<path>` in the warehouse, the record URL in the index, the dataset's path as the search query. A member file (the raw file of an EMPAD pair) is traced through the dataset that holds it. `>` marks the first stage that diverges.

States: `ok`; `missing`; `differs` (holds another version than the stage before); `warn` (search: the dataset is a hit, but not the first); and flags in upper case:

- `BEFORE-HARVEST-WINDOW`: the crawler publishes the record, no closed harvest has its current version, and its datestamp is before the `until` of the last closed harvest (cut to the second, as the harvester sends it), where the next incremental harvest starts; no harvest will take it.
- `SYNCED-WITHOUT-DOCUMENT`: the warehouse marks the record as synced, the index has no document for its URL; the warehouse will not index it again.
- `STALE`: the stage holds the item, the crawler no longer publishes it (a renamed or deleted file).

`status`: T is the start of the newest finished crawl that ended before the end of the chain of closed harvest runs that were all indexed successfully. Every file whose ctime is before T is in the search, unless a trace flags it. This relies on the crawler's store lock (a harvest never reads half-written records) and on the crawler's and the warehouse's clocks agreeing.

## Configuration

Environment variables; the defaults are the e2e stack's service names. Credentials have no defaults.

| Variable | Default |
|---|---|
| `MODAMA_DATA_ROOT` | `/data` |
| `MODAMA_CHAIN_CRAWLER_DB` | `host=crawler-db dbname=modama_crawler user=postgres` (libpq connection string; `PG*` variables apply) |
| `MODAMA_CHAIN_WAREHOUSE_DB` | `host=postgres dbname=datasetdb` (a read-only role suffices) |
| `MODAMA_CHAIN_OAI_URL` | `http://crawler:7654/oai`, also the endpoint's harvest URL in the warehouse |
| `MODAMA_CHAIN_OPENSEARCH`, `MODAMA_CHAIN_INDEX` | `http://opensearch:9200`, `test_datacite` |
| `MODAMA_CHAIN_SEARCH` | `http://search-api:8000` |
| `MODAMA_CHAIN_AIRFLOW`, `_USER`, `_PASSWORD` | `http://airflow-api-server:8080`, an account in the Viewer role (only `status` needs it) |

## What it reads

From the crawler's database, as an interface (change it only together with this tool): `datasets (anchor)`, `members (dataset_id, path)`, `records (identifier, datestamp, metadata->title, metadata->identifier)`, `crawl_runs (started_at, updated_at, finished_at, outcome, counts)`. A run without `finished_at` whose `updated_at` is more than 120 s old is stale. The key rules (`src/modama_chain/crawler.py`) repeat the crawler's, with the namespace and URL prefix read from a stored record.

From upstream (EOSC metadata-warehouse v1.10.0, data-commons-search 0.10.2), all in `src/modama_chain/warehouse.py`: the tables `endpoints`, `harvest_runs`, `harvest_events`, `records`; the record URL as OpenSearch `_id`; `/search?q=&resource=datasets`; runs of the Airflow DAG `warehouse_transform_index` with `harvest_run_id` in their conf.

## Tests

`pytest` here: the rules (flags, rank, T, keys) with canned inputs. Against the real stack: `/prototypes/search-stack/runtest.sh e2e`.
