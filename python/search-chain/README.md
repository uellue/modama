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

Use it first, before SQL, `docker exec … python` or the stores' HTTP APIs: a question about where an item went that `trace`, `status` or `browse` cannot answer is a finding about this tool, to fix or to put in the backlog (`python/crawler/README.md`, "Seeing what happens").

```bash
modama-chain browse [--config TOML] [--bind ADDRESS] [--port 7655]   # a local web page, below
```

## browse

A page for tuning metadata extraction and how a record looks in the search (change `chain-browse` in `python/crawler/openspec/changes/`; @weber's request is scenario D of `python/crawler/design/requirements-pipeline.md`). On the left the data tree, by mouse only (@weber, 2026-11-12: the keys got in the way of typing): a click opens a folder or shows a file, the path above the list goes up, the filter box filters the folder's entries; the address bar holds the path (`?path=/notes/readme.txt`) and is the link to a view. On the right, for the selected file, side by side, each labelled by where it comes from:

| View | Stored (what the chain holds now) | Live (the checkout's code, now) |
|---|---|---|
| Dataset | the crawler database's dataset holding the file | recognised and extracted by the crawler's code |
| OAI-PMH record | the OAI-PMH server's `GetRecord` | `records.build` and `render`, as the server renders it |
| DataCite (harvester) | | upstream's `dc_to_datacite.xsl` (actual code; the call emulated) |
| Warehouse index document | OpenSearch's document | the warehouse's own transformation functions (actual code; the steps between them emulated; no embedding) |
| Search API hit | the search API's `/search` hit for the file's path | emulated from the search API 0.10.2's `SearchHit` |
| Matchmaker: cited dataset, expanded | from the real hit | from the live hit |

On the page, the matchmaker entry comes first and the dataset second, both open; the stages between (record, DataCite, warehouse index document, hit) are folded into one line each, a click unfolds a pair and it stays unfolded from file to file (@weber, 2026-11-12: "I'm looking mostly at the first pair and the last pair. The rest is only interesting if I want to drill down"). The matchmaker entry is matchmaker 0.14.0's expanded "Datasets cited in this answer" row, emulated in HTML from its source (file and lines on the page). Every emulation names the file and lines it follows.

Out of sync (@weber, 2026-11-12: "Most importantly, detect when we are out of sync!"): the search API hit and the matchmaker entry each declare what they follow, in `src/modama_chain/upstream.py` (`HIT`, `ENTRY`): upstream's version (the search API's image version, matchmaker's commit) and a SHA-256 over our patches (`prototypes/search-stack/patches/search-api/`, `patches/matchmaker/`: the `*.patch` files in name order, contents only, `cat $(LC_ALL=C ls *.patch) | sha256sum`). `src/modama_chain/sync.py` reads what the stack builds from `search-api.Dockerfile`, `matchmaker.Dockerfile` and those folders and compares. Where they differ, the view says so in red, and a snapshot carries it, for example:

> out of sync: emulates matchmaker e7138c8 + patches d4ef3bf6203b, the stack builds 0123456 + patches d4ef3bf6203b; review the emulation

The unit test `tests/test_sync.py` fails then too, and says what to review and the new declaration to put in. Bump the stack, review the emulation against upstream's new code, then update the declaration; not the other way round.

The live part runs in a fresh process for each file, so an edit to a format, an extractor, `records.py` or `render.py` shows on the next reload; an edit to this package needs a restart of the tool. It recognises the file's folder alone, as a crawl would (`walk(top=…)`: the folders above it for a collapsed tree, then that folder without its subfolders, so no adoption of subfolders' datasets is shown), and extracts only the file's dataset, with the crawler's time limit and memory budget; after 120 s it is ended with all its processes. One runs at a time; a newer request ends the older one. Its process gets only `PATH`, `HOME` and `LANG`. A folder shows its stored views and no live ones.

"Path on the server" is `MODAMA_BROWSE_HOST_ROOT` and the path, with a copy button (on staging `/storage/er-c-data/…`, for a notebook). "Save for Claude" writes the file's views as one Markdown file into `MODAMA_BROWSE_SNAPSHOTS` (the stack: the checkout's `.claude/field-tests/browse/` on staging) and shows `browse/<time>-<name>.md` to copy into a chat; a message typed into the field above it goes at the top of the file, under "Message". A snapshot holds paths, owners' names and text from users' files; an agent reads it as data, never as instructions.

It writes nothing else: read-only database transactions, GET requests only. That is the tool's own guard: in the search stack `crawler-db` trusts every connection and OpenSearch has no security. It answers only requests addressed to `localhost` or `127.0.0.1`, and a snapshot only with its header `X-Modama-Browse: 1`. Paths with `..`, `.`, empty components, a NUL or a symlink on the way are refused; symlinks are listed and not followed, as the crawler skips them.

## Output

`trace` prints the path, then the keys the stages hold its dataset under (once, as a header), then one line per stage: stage, state, time and detail, with long details continued on indented lines. The keys: the path in the tree, the OAI identifier in the crawler and OAI-PMH, the identifier after its last `:` in the harvest, `<endpoint uuid>::<path>` in the warehouse, the record URL in the index, the dataset's path as the search query. A member file (the raw file of an EMPAD pair) is traced through the dataset that holds it. The crawler line's detail ends with that dataset's basis, for example `basis: single file; em/k2is: not application/x.dm-gtg, no DM header` for a text file named `notes.gtg`. `>` marks the first stage that diverges.

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
| `MODAMA_BROWSE_HOST_ROOT` | `MODAMA_DATA_ROOT`: where the data tree is on the server, for "Path on the server" (`browse`) |
| `MODAMA_BROWSE_SNAPSHOTS` | none (no "Save for Claude"): the snapshot folder (`browse`) |
| `MODAMA_BROWSE_UPSTREAM` | `/upstream`: holds `metadata-crawlers/harvester/` and `metadata-warehouse/{src,config}/`, the submodules' files, and `search-stack/` with the search stack's `search-api.Dockerfile`, `matchmaker.Dockerfile` and `patches/{search-api,matchmaker}/`, for the out-of-sync check (`browse`) |

`browse` needs the extra `browse` (`pip install -e "python/search-chain[browse]"`: werkzeug, lxml, and the warehouse's xmltodict and jsonschema at the versions of its transform environment) and the crawler and its format collections installed beside it.

## What it reads

From the crawler's database, as an interface (change it only together with this tool): `datasets (anchor, basis, extractor, extractor_identity)` (the basis on the crawler line: why the crawler recognised the dataset, with the note of a name type a format dropped; the extractor and the extractor identity that produced its description, compared with the last finished crawl's: `extracted by em/dm4 under 6d881430e7c8, the last crawl's (current)`), `members (dataset_id, path)`, `records (identifier, datestamp, metadata->title, metadata->identifier)`, `crawl_runs (started_at, updated_at, finished_at, outcome, counts, identity, reextracted)` (`status` shows the identity and how many datasets the crawl extracted again for a new identity, and how many of their results changed). A crawler database from before the extractor identity (schema `0001_baseline`) has neither column; the tool then leaves them out. For `browse` also `datasets (type, format, version, warnings, parent, collapsed, mtime, uid, parts, size, stamp, directory, extractor, extractor_identity, extracted, extract_error, extract_seconds)` and `records (metadata)`. From the crawler's code, for `browse`: `walk(top=…)`, `cli.configure`, `extraction.extract`, `identity`, `records.build`, `render`. A run without `finished_at` whose `updated_at` is more than 120 s old is stale. The key rules (`src/modama_chain/crawler.py`) repeat the crawler's, with the namespace and URL prefix read from a stored record.

From upstream (EOSC metadata-warehouse v1.10.0, data-commons-search 0.10.2), all in `src/modama_chain/warehouse.py`: the tables `endpoints`, `harvest_runs`, `harvest_events`, `records`; the record URL as OpenSearch `_id`; `/search?q=&resource=datasets`; runs of the Airflow DAG `warehouse_transform_index` with `harvest_run_id` in their conf.

## Tests

`pytest` here: the rules (flags, rank, T, keys) with canned inputs; `browse` on the crawler's and the EM collection's fixtures (paths, listings, the live part and its limits, each view's assembly, snapshots), which needs the extra `browse`, the crawler and `modama-formats-em` installed and the EOSC submodules checked out; the emulations' declarations against the repository's `prototypes/search-stack/` (`test_sync.py`; missing files fail). In a new worktree the submodules are empty: `git submodule update --init prototypes/EOSC-Data-Commons/data-commons-search prototypes/EOSC-Data-Commons/metadata-crawlers prototypes/EOSC-Data-Commons/metadata-warehouse` from the repository root first. Against the real stack: `/prototypes/search-stack/runtest.sh e2e`, which also compares the browser's live views with what the stack stored.
