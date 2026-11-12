# Design

## Context

The chain (`python/search-chain/README.md`): tree → crawler (recognition, extraction, `records.build`, the records table) → OAI-PMH server (`render`) → harvester (oai_dc → DataCite by upstream's `dc_to_datacite.xsl`, a harvest event) → warehouse transform (DataCite XML → JSON, normalised, validated, embedded, indexed in OpenSearch under the record URL) → search API (`/search`, `SearchHit` with computed fields) → matchmaker (the hit, rendered; in the chat, the cited datasets under an answer). `modama-chain` already reads the crawler database, the warehouse database, OpenSearch and the search API, read-only, with the stack's read-only accounts (`chain.env`).

Where the code of each stage lives, and whether the tool can run it:

| Stage | Code | In the tool |
|---|---|---|
| recognition, extraction, record | `python/crawler`, `python/modama-formats-em` (installed editable in the crawler image) | actual code, from the checkout |
| oai_dc XML | `modama_crawler.render` | actual code |
| DataCite | `metadata-crawlers` at `9c120f5` (submodule; the Airflow image installs the same ref, `HARVESTER_REF`): `harvester/dc_to_datacite.xsl`, applied by `apply_xslt_transform` (`harvester_oaipmh.py:21-35`) | the XSLT is actual; the 4-line call is emulated (D7) |
| index document | `metadata-warehouse` v1.10.0 (submodule): `utils/handle_xml.py`, `utils/normalize_datacite_json.py`, `config/schema.json`; the loop body of `transform_batch_impl` (`transform/transform_core.py:149-188`) | the functions are actual; the loop body is emulated (D8) |
| search hit | data-commons-search 0.10.2, inside the image only (the submodule is at v0.7.13-3, older): `models.py:182-251` | emulated (D9); the real hit from `/search` when indexed |
| cited dataset | matchmaker 0.14.0 (`e7138c8`) with `patches/matchmaker/0001-0003`, TypeScript/React | emulated (D10) |

The leans of the coordinator's brief (2026-11-12) are taken as assumptions; each decision says where it follows one and where it deviates.

## Decisions

### D1. Home: `modama-chain browse` (lean 1, as agreed)

A subcommand of `modama-chain`, which already reads every store of the chain. Four modules: `browse.py` (the WSGI app: routes, paths, the page, snapshots), `views.py` (the views of one path, from the stores and from `live`), `live.py` (the crawler part, run as a child process, D4), `upstream.py` (what the tool knows of the harvester's, the warehouse's, the search API's and matchmaker's code, with file and line of each). Deviation from chain-trace D4 ("everything this tool knows about upstream internals, in one place", `warehouse.py`): `warehouse.py` stays the stores' interface; the conversions are a second kind of knowledge, code run or emulated rather than tables read, and they import upstream modules from paths that only exist where the submodules are mounted. Both modules say so in their docstrings.

The web server is werkzeug, as the crawler's OAI-PMH server; the page is one HTML file with its CSS and a little JavaScript inline, no library.

### D2. A service `browse` in the search stack (lean 2, with snapshots as the one write)

In `docker-compose.yml`: image `search-stack-browse`, built by `browse.Dockerfile` `FROM search-stack-crawler` (the pattern of `warehouse-airflow.Dockerfile`), which adds the extra `browse` (D15) and `git` (D13). It does not touch the crawler's image or service definition, so starting it never recreates `crawler` or `crawl-timer`.

- Command `modama-chain browse` on `0.0.0.0:7655` inside; published on `127.0.0.1:7655` (test) and `127.0.0.1:17655` (staging), next to the crawler's 7654 and 17654.
- Read-only mounts: the sources at the paths the image's editable installs point to (`python/crawler/src` → `/src/src`, `python/modama-formats-em/src` → `/em/src`, `python/search-chain/src` → `/chain/src`), so the checkout's code runs; upstream's `harvester/` and the warehouse's `src/` and `config/` under `/upstream/`; the data tree (test: the volume `testdata`; staging: `STAGING_DATA`, as the crawler: `create_host_path: false`, `recursive: readonly`); sssd's sockets.
- `chain.env` (the read-only accounts), `MODAMA_DATA_ROOT=/data`; staging: `user: STAGING_USER`, `group_add: STAGING_GROUP`, the crawl's TOML (`--config /stagingconf/$STAGING_CRAWL_CONFIG`, so the live recognition uses the crawl's formats and exclusions), and `MODAMA_BROWSE_HOST_ROOT=$STAGING_DATA` for the path on the server (D11).
- Writes: only snapshots (D13), into one mounted folder. No database writes, no HTTP request that changes anything, no file in the data tree.
- `depends_on`: `crawler-db`, `sssd` healthy; nothing that starts a crawl. On staging it is started alone: `dc up -d --no-deps browse`.

### D3. Not disturbing a crawl, a harvest or an indexing run

- Database reads in read-only transactions (`chain.connect`), no advisory locks: PostgreSQL readers never block a crawl's store (MVCC), unlike the OAI-PMH server's shared store lock.
- At most one live computation at a time: a new one ends the running one (one person uses the tool; the page cancels its own stale requests).
- The live computation runs in its own process group with one extraction worker, the crawler's memory budget per worker (`extraction.MEMORY`) and its time limit per dataset (`extraction.TIME_LIMIT`, 60 s); the group is killed after twice that, 120 s, walk included, and the view says so.
- No CPU weight of its own: it answers a person, as the search API does (requirements-pipeline 2.4, "Priority").

### D4. Live: the crawler's code in a fresh child process per file (lean 4b)

`live.py` is run as `python -m modama_chain.live [--config TOML] PATH` with no shell; it prints one JSON document: the crawler's settings and formats from the TOML (`selection.load_config`, `discover`, `enabled_formats`, `enabled_collections`, `mimedb.build`, as `modama-crawler records` does), `walk(root, formats, top=<the file's folder>, …)` (D5), `extraction.extract(…, workers=1)` inside `cpus.set_num_threads_env(1)`, `records.format_names` and `records.build`, and the dataset holding the path with its extraction and warnings. A fresh interpreter per file imports the checkout's current code, so an edit to a format, an extractor or `records.py` shows on the next reload without a rebuild, a re-crawl or a restart. Edits to `render.py`, `upstream` code (pinned submodules) or `modama_chain` itself need `docker compose restart browse` (seconds; the server process imported them). A new format's entry point needs the image rebuilt (`pip install -e` writes entry points at build time).

Cost per file: an interpreter, the MIME database (built per process, as each crawl does), the folder's listing and MIME detection, one extraction. Measured in the spike; the page shows the stored views first and fills in the live ones.

### D5. `walk(top=…)`: one folder recognised as the crawl recognises it

The dataset of a file depends on the pre-order calls of every folder above it (any may collapse the tree: a Zarr store, a `.git`), on its folder's listing and MIME types, and on its folder's subdirectories' datasets (a collection format may adopt them as parts). `walk(root, formats, top="/a/b")` lists each folder from the root down to `/a`, runs its pre-order call and stops at the first that collapses (returning that dataset); otherwise it walks `/a/b` with all its subdirectories, as the crawl would, with paths relative to the root, the exclusions and per-path ignores applied as in the crawl. If `top` or a folder on the way is excluded, a symlink or not a directory, the result is empty. A crawl calls `walk` without `top` and is unchanged.

Limits, stated in the view: a dataset adopted by a format in the folder above (none of today's formats adopts; `collection` is false everywhere) would lack its parent relation; a folder with a large subtree may not finish within D3's limit, and the view then says so.

Alternative rejected: rebuilding the walk's listing and pre-order calls in `modama-chain` from the crawler's public pieces (`Directory`, `run_pre`, `Entry`): a copy of `walk.py`'s `entries_of` to keep in sync, which is what the request rules out.

### D6. Stored views (lean 4a)

From the crawler database (read as an interface, README "What it reads", extended): the dataset holding the path (anchor itself, member, or under a collapsed anchor), its row (`format`, `type`, `version`, `basis`, `warnings`, `extractor`, `extractor_version`, `extracted`, `extract_error`, `collapsed`, `directory`) and members; the record's `datestamp` and `metadata`. The record as the OAI-PMH server serves it: its `GetRecord` response (the actual server). The trace: `chain.trace` and `cli.trace_lines` (actual code).

The live record gets the stored record's datestamp when its metadata equals the stored metadata, else the time of the view and a note "differs from the stored record: the next crawl gives it a new datestamp". So an unchanged file's live `<record>` equals the server's byte for byte, which the e2e test checks.

### D7. The harvester's conversion (lean 4c, deviating in how it is called)

The XSLT is the submodule's `dc_to_datacite.xsl` (the same commit the Airflow image installs), applied as `apply_xslt_transform` does: `ET.XSLT(ET.parse(xsl))(ET.fromstring(record_xml))`, serialised with `pretty_print=True, encoding="UTF-8"`; its input is the `<record>` element, as oaipmh-scythe hands it to `process_record` (`ET.tostring(record.xml)`). Deviation: the harvester's own `transformation_and_additional_metadata` is not imported, because importing any module of the package runs `harvester/__init__.py`, which imports `main` and with it `httpx`, `oaipmh_scythe`, `pydantic_settings` and `SPARQLWrapper`, none of which the crawler image has. Labelled "upstream's XSLT; the call emulated (harvester_oaipmh.py:21-35, 77-86)". lxml is the crawler image's (6.1.3), not the harvester venv's; the e2e test compares the result with the harvest event the warehouse stored.

### D8. The warehouse's index document (lean 4d)

The warehouse's own functions, imported from the submodule (`/upstream/warehouse/src` on `sys.path`): `handle_xml.detect_metadata_namespace`, `detect_payload_namespace`, `preprocess_xml`, `get_resource`; `xmltodict.parse(…, process_namespaces=True)`; `normalize_datacite_json.normalize_datacite_json`; validation against `config/schema.json` with jsonschema (`validate`, which patch 0001 shows to be equivalent to the image's validator). The loop body that strings them together (`transform_core.py:149-188`) and the fields added after it (`_additional_metadata`: the oai_dc record, `_repo`: the endpoint's repository code from the warehouse database, `_harvest_url`: the OAI-PMH URL; `utils/embedding_utils.py:70-76`) are emulated, about 20 lines, because the function also embeds, writes to PostgreSQL and indexes. `emb` is left out: computing it needs the embedding model, and it is not shown (a vector). The stored document is OpenSearch's `_source` for `_id` = the record URL, `emb` shown as its length.

### D9. The search API's hit (lean 4e, part)

Stored: the real `/search?q=<anchor>&resource=datasets` response's hit whose `_source.url` is the record URL (the trace's rule), as matchmaker receives it. Live: `SearchHit` emulated from the 0.10.2 image's `models.py` (`dataset_url` 200-215, `title` 217-225, `description` 227-235, `creator` 237-242, `publication_date` 244-251; `_source` limited to `SearchHitSrc`'s fields, 164-179), without `score` (the reranker needs a query). The e2e test compares the emulation, fed with the stored index document, with the real hit.

### D10. Matchmaker's expanded entry (lean 4e)

Emulated in HTML and CSS from matchmaker 0.14.0 (`e7138c8` with patches 0001-0003): the row (`CitedDatasets.tsx:69-115`: number, repository name, title, year · first two creators, Source link) and the expanded part (`SearchResultItem.tsx:27-48` relevance badge when the hit has a score, `51-152` description cut at 300 characters with "Show more", creators (three, "+N more"), publication date as `YYYY.MM.DD`, subjects (five, "+N more")); `utils.ts` `stripHtml`, `publicationDateOf`, `formatPublicationDate`; `repoProvenance.ts:160-171` (an unknown repository code is shown as text). Labelled "emulated from matchmaker 0.14.0 …" with the file and lines. Not rendered: logos, Play, Cite, the "Cited from" strip, the tracking. Running the React component server-side is out (no Node.js or dev dependencies in the image).

### D11. Navigation without mode change (lean 3)

One page: on the left the folder (breadcrumb, a filter field, the entries in a virtual list that draws only the visible rows), on the right the views of the selected entry. Keys: ↑/↓ move, Enter or → opens a folder, Backspace or ← goes up, `/` focuses the filter, Esc leaves it. The URL is `?path=/a/b/file` (a file: its folder listed, the file selected) or `?path=/a/b/` (a folder); moving the selection replaces the URL, opening a folder pushes it, so Back works. The listing is one `os.scandir` (names and kinds from the directory entries, no `stat` per entry); 67,600 entries are one JSON response. Views load after the selection rests for 300 ms, the stored ones first.

The path on the server (the request's "full storage path on ptycho"; the glossary's _canonical path_ under the data tree's mount point, `/CONTEXT.md` avoids "storage path"): `MODAMA_BROWSE_HOST_ROOT` + the path; in the test stack, without the variable, the path inside the container. Copy buttons for it and for the view's link.

### D12. Paths

A path is relative to the data root and starts with `/`; it is refused (HTTP 400, nothing read) when it does not, when it contains a NUL or an empty, `.` or `..` component, or when any component on the way is a symlink (the crawler skips symlinks, so nothing behind one is in the chain), checked component by component with `lstat` from the root; the resolved path must be under the root's real path. Listings and `lstat` errors (permission) are shown as the file system reports them, never inferred from mode bits (top-level `AGENTS.md`).

### D13. Snapshots for the chat (the coordinator's lean of 2026-11-12)

"Save for Claude" (POST) writes one Markdown file: the path and the path on the server, the time, the checkout's commit and the files changed against it under `python/` (`git rev-parse HEAD`, `git status --porcelain -- python/`, with the checkout's `.git` mounted read-only; `git` in the image), the extractor identity (format id, version, extractor version), and every view's content in fenced blocks (stored dataset and record, trace, live dataset and record, DataCite, index document live and stored, the search hit live and real, the matchmaker entry as text). Name: `<UTC time>-<file name, reduced to [A-Za-z0-9._-], at most 60 characters>.md`, for example `2026-11-12T19-05-03-spectrum.dm4.md`; the page shows `browse/<name>` with a copy button. The folder is mounted read-write as the only writable path: on staging the checkout's `.claude/field-tests/browse/` (gitignored with `.claude/`), which must exist (the staging commands create it, so that Docker does not create it as root); in the test stack a volume. Snapshots hold paths and owners' names (accepted internally, decision 200), never a credential: the views are built from documents, not from the environment, and a test checks that no value of the environment's credentials appears.

Alternative: the git commit given at start in an environment variable: stale after a `git pull` without a restart, and silent about uncommitted edits, which are what is being tuned.

### D14. Security

Read-only mounts and accounts (D2); no shell (child processes with argument lists); bound to 127.0.0.1 on the host; requests whose `Host` is not `localhost` or `127.0.0.1` refused (DNS rebinding); the snapshot POST requires a custom header, which a cross-site form cannot send without a CORS preflight that the server never answers; HTML escaping of every value (paths and metadata come from users' files); no connection string, password or environment value in a page, a snapshot or a log line (errors of the stores are shown by store name and the library's message, as `modama-chain` does).

### D15. Dependencies (to be confirmed)

- `xmltodict` 1.0.4 and `jsonschema` 4.26.0 (both the current release on PyPI, checked 2026-11-12), pinned to what the warehouse's transform environment runs (`metadata-warehouse/uv.lock`, v1.10.0), in an extra `browse` of `modama-chain`, installed only in the browse image. MIT each. Without them D8 would be emulated too.
- `git` (Debian trixie) in the browse image, for D13.

## Risks

- **Version skew:** the live views run the checkout's code, the stored ones what the deployed images ran. That is the point (stored vs live), but a staging checkout ahead of the images shows differences that a re-crawl would bring. The page shows the checkout's commit.
- **Emulations drift** from upstream (D7 call, D8 loop, D9, D10). Mitigation: file and line references in the code and the page; the e2e test compares D7, D8 and D9 with what the stack stored; D10 is checked by eye against matchmaker.
- **Large folders:** live recognition of a folder with 67,600 files reads their types (stat and magic over NFS); it may hit the limit (D3). Measured on staging by @weber; a cache per folder listing is a next step if needed.
- **The tool's own load** on staging: one live computation at a time, one extraction worker.

## Not now

A search box; the stored DataCite of the last harvest event; the embedding text; rendering matchmaker's real component; a shallower live recognition for folders with large subtrees; the same in `deploy/`.
