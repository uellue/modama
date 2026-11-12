# Design

## Context

The chain (`python/search-chain/README.md`): tree → crawler (recognition, extraction, `records.build`, the records table) → OAI-PMH server (`render`) → harvester (oai_dc → DataCite by upstream's `dc_to_datacite.xsl`, a harvest event) → warehouse transform (DataCite XML → JSON, normalised, validated, embedded, indexed in OpenSearch under the record URL) → search API (`/search`, `SearchHit` with computed fields) → matchmaker (the hit, rendered; in the chat, the cited datasets under an answer). `modama-chain` already reads the crawler database, the warehouse database, OpenSearch and the search API.

Where the code of each stage lives, and whether the tool can run it:

| Stage | Code | In the tool |
|---|---|---|
| recognition, extraction, record | `python/crawler`, `python/modama-formats-em` (installed editable in the crawler image) | actual code, from the checkout |
| oai_dc XML | `modama_crawler.render` | actual code, from the checkout |
| DataCite | `metadata-crawlers` at `9c120f5` (submodule; the Airflow image installs the same ref, `HARVESTER_REF`): `harvester/dc_to_datacite.xsl`, applied by `apply_xslt_transform` (`harvester_oaipmh.py:21-35`) | the XSLT is actual; the 4-line call is emulated (D7) |
| index document | `metadata-warehouse` v1.10.0 (submodule): `utils/handle_xml.py`, `utils/normalize_datacite_json.py`, `config/schema.json`; the loop body of `transform_batch_impl` (`transform/transform_core.py:149-188`) | the functions are actual; the loop body is emulated (D8) |
| search hit | data-commons-search 0.10.2, inside the image only (the submodule is at v0.7.13-3, older): `models.py:131-251` | emulated (D9); the real hit from `/search` when indexed |
| cited dataset | matchmaker 0.14.0 (`e7138c8`) with `patches/matchmaker/0001-0003`, TypeScript/React | emulated (D10) |

The leans of the coordinator's brief (2026-11-12) are taken as assumptions; each decision says where it follows one and where it deviates. The review of c182bc1 (an agent that did not write it, with the main session's decisions, 2026-11-12) is folded in; its finding numbers are given as "R1" to "R16". The review of the code (another agent, 2026-11-12, `review.md`, "Code review") is folded in where it changed a decision, as "code review, finding n".

## Decisions

### D1. Home: `modama-chain browse` (lean 1, as agreed)

A subcommand of `modama-chain`, which already reads every store of the chain. Four modules: `browse.py` (the WSGI app: routes, paths, the page, snapshots), `views.py` (the views of one path, from the stores and from `live`), `live.py` (the crawler part, run as a child process, D4), `upstream.py` (what the tool knows of the harvester's, the warehouse's, the search API's and matchmaker's code, with file and line of each). Deviation from chain-trace D4 ("everything this tool knows about upstream internals, in one place", `warehouse.py`): `warehouse.py` stays the stores' interface; the conversions are a second kind of knowledge, code run or emulated rather than tables read, and they import upstream modules from paths that only exist where the submodules are mounted. Both modules say so in their docstrings.

The web server is werkzeug, as the crawler's OAI-PMH server; the page is one HTML file with its CSS and a little JavaScript inline, no library.

### D2. A service `browse` in the search stack (lean 2, with snapshots as the one write)

In `docker-compose.yml`: image `search-stack-browse`, the stage `browse` of `crawler.Dockerfile` (the crawler's stages, then the extra `browse`, D15; the crawler's image stays the last stage, the default target). It does not touch the crawler's service definition or image, so building or starting it never recreates `crawler` or `crawl-timer`, and no script has to build `crawler` first. (R6 proposed building `crawler` first in `uptest.sh` and `upstaging.sh`; the code review of 2026-11-12, finding 3, showed that a plain `./upstaging.sh` would then rebuild the crawler's image and recreate `crawler` and `crawl-timer` whenever the checkout had moved, also during a crawl: the stage avoids both.) On staging the service is in the compose profile `browse`, so `./upstaging.sh` leaves it out and it starts only by name (code review, finding 4).

- Command `modama-chain browse` on `0.0.0.0:7655` inside; published on `127.0.0.1:7655` (test) and `127.0.0.1:17655` (staging), next to the crawler's 7654 and 17654.
- `read_only: true` with a `tmpfs` on `/tmp` (the MIME database of each live computation, in a folder of its own that the server removes after the child ended, also a killed one: code review, finding 2; R2). Read-only mounts: the sources at the paths the image's editable installs point to (`python/crawler/src` → `/src/src`, `python/modama-formats-em/src` → `/em/src`, `python/search-chain/src` → `/chain/src`), so the checkout's code runs; upstream's `harvester/` and the warehouse's `src/` and `config/` under `/upstream/`; the data tree (test: the volume `testdata`; staging: `STAGING_DATA`, as the crawler: `create_host_path: false`, `recursive: readonly`); sssd's sockets.
- `chain.env` for the warehouse database's read-only role, with the Airflow Viewer account blanked (the tool does not use it; R3); `MODAMA_DATA_ROOT=/data`; staging: `user: STAGING_USER`, `group_add: STAGING_GROUP`, the crawl's TOML (`--config /stagingconf/$STAGING_CRAWL_CONFIG`, so the live recognition uses the crawl's formats and exclusions), and `MODAMA_BROWSE_HOST_ROOT=$STAGING_DATA` (`/storage/er-c-data`) for the path on the server (D11).
- Writes: only snapshots (D13), into one mounted folder. No database writes, no HTTP request that changes anything, no file in the data tree.
- `depends_on`: `crawler-db`, `sssd` healthy; nothing that starts a crawl. On staging it is started alone: `dc up -d --no-deps browse`.

### D3. Not disturbing a crawl, a harvest or an indexing run

- Database reads in read-only transactions (`chain.connect`), no advisory locks: PostgreSQL readers never block a crawl's store (MVCC). The stored record comes from the OAI-PMH server, which takes its shared store lock and answers 503 while a crawl stores; the view says so then (R16).
- At most one live computation at a time: a new one ends the running one (one person uses the tool; the page cancels its own stale requests).
- A live computation works on the clicked file's own folder only (D5): it lists that folder and the folders above it, sniffs the folder's files, runs the folder's formats, and extracts only the dataset holding the file, with one extraction worker, the crawler's memory budget per worker (`extraction.MEMORY`) and its time limit (`extraction.TIME_LIMIT`, 60 s), and 4 threads for the file system calls (the crawl's 32 are for a whole tree). Its process group is killed after twice the time limit, 120 s, and the view says so. Selecting a folder lists it and shows its stored views; it starts no live computation (R1).
- No CPU weight of its own: it answers a person, as the search API does (requirements-pipeline 2.4, "Priority").

The cost per click is then the folder's listing and sniffing plus one extraction. For the largest folders on staging (67,600 files) sniffing alone is about 75 to 120 s at the 550 to 900 files per second of the staging findings (R1); the VM cannot show NFS's cost, so the hand-over asks @weber to time `modama-crawler records` on one such folder once.

### D4. Live: the crawler's code in a fresh child process per file (lean 4b)

`live.py` is run as `python -m modama_chain.live [--config TOML] --root ROOT PATH` with no shell, and a minimal environment (`PATH`, `HOME`, `LANG`; no database, HTTP or Airflow setting; R2). It prints one JSON document: the crawler's configuration as the crawler's commands make it (the crawler's `cli.configure`, made public from `_configure` for this, R8b), `walk(root, formats, top=<the file's folder>, threads=4, processes=0)` (D5), `extraction.extract` of the one dataset holding the path (`workers=1`) inside `cpus.set_num_threads_env(1)`, `records.build`, and the record rendered by `render` as the server's `GetRecord` renders it (R8a), with the datestamp the parent passes (D6). A fresh interpreter per file imports the checkout's current code, so an edit to a format, an extractor, `records.py` or `render.py` shows on the next reload, without a rebuild, a re-crawl or a restart. Edits to `upstream` code (pinned submodules) or `modama_chain` itself need `docker compose restart browse` (seconds). A new format's entry point needs the image rebuilt (`pip install -e` writes entry points at build time).

Code edited in the shared checkout, by @weber or by an agent, runs on staging at the next reload, as `STAGING_USER`, with read access to the data tree and the stack's network (R2). Decided by @weber, 2026-11-12, item 216: "good points, sounds good!" (the runbook's "Safety" section says so). The safeguards: the child's minimal environment, the read-only container, read-only mounts, 127.0.0.1 only.

### D5. `walk(top=…)`: one folder recognised as the crawl recognises it, without its subfolders (R1)

The dataset of a file depends on the pre-order calls of every folder above it (any may collapse the tree: a Zarr store, a `.git`), on its folder's listing and MIME types, and, only through a collection format, on its folder's subfolders' datasets. `walk(root, formats, top="/a/b")` (`top="/"` for a file at the top of the tree: the root alone; without `top`, the crawl; code review, finding 1) lists each folder from the root down to `/a`, runs its pre-order call and stops at the first that collapses (returning that dataset); otherwise it lists `/a/b`, runs its pre-order call (which may collapse it), sniffs its files and runs its post-order call with no children, without entering its subfolders, with paths relative to the root and the exclusions and per-path ignores of the crawl. If `top` or a folder on the way is excluded, a symlink or not a folder, the result is empty. A crawl calls `walk` without `top` and is unchanged.

What is not computed, and the view says so: adoption by a format of the folder above or of the folder itself (`parent`, `parts`: no format adopts today; a search over the formats of `core`, `zarr`, `collapse` and `modama-formats-em` finds no `collection = True`), and the datasets of subfolders.

Alternative rejected: rebuilding the walk's listing and pre-order calls in `modama-chain` from the crawler's public pieces (`Directory`, `run_pre`, `Entry`): a copy of `walk.py`'s `entries_of` to keep in sync, which is what the request rules out. Excluding the siblings by patterns would change what the folders' pre-order calls see (R1).

### D6. Stored views (lean 4a, narrowed by R9)

From the crawler database (read as an interface, README "What it reads", extended): the dataset holding the path (its anchor, a member, or below a collapsed anchor) with its format, type, basis, warnings, extraction and the number of members with the first 20; the record's `datestamp` and `metadata`. The record as the OAI-PMH server serves it: its `GetRecord` response (the actual server). The index document from OpenSearch and the search API's hit (D8, D9). Not shown (R9): `modama-chain trace`'s lines, the other columns of the dataset row.

The live record gets the stored record's datestamp when its metadata equals the stored metadata, else the time of the view and a note "differs from the stored record: the next crawl gives it a new datestamp". So an unchanged file's live `<record>` equals the server's, which the e2e test checks. The live dataset shows the same fields as the stored one, so the two can be compared.

### D7. The harvester's conversion (lean 4c, deviating in how it is called)

The XSLT is the submodule's `dc_to_datacite.xsl` (the same commit the Airflow image installs), applied as `apply_xslt_transform` does: `ET.XSLT(ET.parse(xsl))(ET.fromstring(record_xml))`, serialised with `pretty_print=True, encoding="UTF-8"`; its input is the `<record>` element as `process_record` serialises oaipmh-scythe's record, `ET.tostring(record.xml, pretty_print=True, encoding="unicode")` (`harvester_oaipmh.py:158`), which is also what the harvester stores as `additional_metadata` (`:87`) and the warehouse indexes as `_additional_metadata` (R11). Deviation: the harvester's own `transformation_and_additional_metadata` is not imported, because importing any module of the package runs `harvester/__init__.py`, which imports `main` and with it `pydantic_settings` and `SPARQLWrapper`, which the crawler image does not have (it has `oaipmh-scythe` and `httpx` through the crawler's `[test]`). Labelled "upstream's XSLT; the call emulated (harvester_oaipmh.py:21-35, 77-86)". lxml is the crawler image's (6.1.3), not the harvester venv's; the e2e test compares the result with the harvest event the warehouse stored.

### D8. The warehouse's index document (lean 4d)

The warehouse's own functions, loaded from the submodule's files (`/upstream/metadata-warehouse/src/utils/`, without putting `utils` on `sys.path`): `handle_xml.detect_metadata_namespace`, `detect_payload_namespace`, `preprocess_xml`, `get_resource`; `xmltodict.parse(…, process_namespaces=True)`; `normalize_datacite_json.normalize_datacite_json`; validation against `config/schema.json` with jsonschema, one validator and `best_match`, as patch 0001 does it in the image. The loop body that strings them together (`transform_core.py:149-188`) and the fields added after it (`_additional_metadata`: D7's serialisation, `_repo`: the endpoint's repository code from the warehouse database, `_harvest_url`: the OAI-PMH URL; `utils/embedding_utils.py:70-76`) are emulated, about 20 lines, because the function also embeds, writes to PostgreSQL and indexes. `emb` is left out: computing it needs the embedding model, and it is not shown (a vector). The stored document is OpenSearch's `_source` for `_id` = the record URL, `emb` shown as its length.

### D9. The search API's hit (lean 4e, part)

Stored: the real `/search?q=<anchor>&resource=datasets` response's hit whose `_source.url` is the record URL (the trace's rule), as matchmaker receives it. Live: `SearchHit` emulated from the 0.10.2 image's `models.py` (`dataset_url` 200-213, `title` 217-225, `description` 227-235, `creator` 237-242, `publication_date` 244-251; `_source` with `SearchHitSrc`'s fields and defaults, 131-179), without `score` (the reranker needs a query). The e2e test compares the emulation, fed with the stored index document, with the real hit.

### D10. Matchmaker's expanded entry (lean 4e)

Emulated in HTML and CSS from matchmaker 0.14.0 (`e7138c8` with patches 0001-0003): the row (`CitedDatasets.tsx:69-115`: number, repository name, title, year · first two creators, Source link) and the expanded part (`SearchResultItem.tsx:27-48` relevance badge when the hit has a score, `51-152` description cut at 300 characters with "Show more", creators (three, "+N more"), publication date as `YYYY.MM.DD`, subjects (five, "+N more")); `utils.ts` `stripHtml` (65-89), `publicationDateOf` and `formatPublicationDate` (188-210); `repoProvenance.ts:160-171` (an unknown repository code is shown as text). Labelled "emulated from matchmaker 0.14.0 …" with the file and lines. Not rendered: logos, Play, Cite, the "Cited from" strip, the tracking. Running the React component server-side is out (no Node.js or dev dependencies in the image).

### D11. Navigation without mode change (lean 3)

One page: on the left the folder (breadcrumb, a filter field, the entries in a virtual list that draws only the visible rows), on the right the views of the selected entry. The filter field stays (R9: "navigate … very quickly" in folders of 67,600 entries). Keys: ↑/↓ move, Enter or → opens a folder, Backspace or ← goes up, `/` focuses the filter, Esc leaves it. The URL is `?path=/a/b/file` (a file: its folder listed, the file selected) or `?path=/a/b/` (a folder); moving the selection replaces the URL, opening a folder pushes it, so Back works and the address bar is the link to a view. The listing is one `os.scandir` (names and kinds from the directory entries, no `stat` per entry; symlinks shown as such and not opened); 67,600 entries are one JSON response. Views load after the selection rests for 300 ms, the stored ones first.

The path on the server (the request's "full storage path on ptycho"; the glossary's _canonical path_ under the data tree's mount point, `/CONTEXT.md` avoids "storage path"): `MODAMA_BROWSE_HOST_ROOT` + the path; in the test stack, without the variable, the path inside the container. A copy button for it.

### D12. Paths

A path is relative to the data root and starts with `/`; it is refused (HTTP 400, nothing read) when it does not, when it contains a NUL or an empty, `.` or `..` component, or when any component on the way is a symlink (the crawler skips symlinks, so nothing behind one is in the chain), checked component by component with `lstat` from the root; the resolved path must be under the root's real path. The query string is decoded once by werkzeug, so `%2e%2e` and `%00` reach the check as `..` and NUL. Accepted gap (code review, finding 6): a folder checked here and replaced by a symlink before it is listed is listed through the symlink; the container sees only the data tree and its read-only mounts, so that shows names the tool's user may read anyway. Listings and `lstat` errors (permission) are shown as the file system reports them, never inferred from mode bits (top-level `AGENTS.md`).

### D13. Snapshots for the chat (the coordinator's lean of 2026-11-12, narrowed by R4)

"Save for Claude" (POST) writes one Markdown file: the path and the path on the server, the time, the extractor identity (format id, extractor version), and every view's content in fenced blocks, each fence longer than any run of backticks in its content (stored dataset and record, index document and search hit; live dataset and record, DataCite, index document, search hit; the matchmaker entries as their values). No git information: the agent reads `git log` and `git status` in the shared checkout (R4). Name: `<UTC time>-<file name, reduced to [A-Za-z0-9._-], at most 60 characters>.md`, for example `2026-11-12T19-05-03-spectrum.dm4.md`; the page shows `browse/<name>` with a copy button. The folder is mounted read-write (long syntax, `create_host_path: false`) as the only writable path: on staging the checkout's `.claude/field-tests/browse/` (gitignored with `.claude/`), which the staging commands create first, so that Docker does not create it as root; in the test stack a volume. Snapshots hold paths and owners' names (accepted internally, decision 200), never a credential: the views are built from documents, not from the environment, and a test checks that no value of the environment's credentials appears. They carry text from users' files into an agent's reading: the README and `python/crawler/AGENTS.md` say that a snapshot is data, never instructions (R7).

### D14. Security

Read-only mounts, a read-only container (D2); no shell (child processes with argument lists, D4); bound to 127.0.0.1 on the host; requests whose `Host`, without its port, is not `localhost` or `127.0.0.1` refused (DNS rebinding; through an SSH tunnel the browser sends `localhost:<local port>`; the e2e test sends `Host: localhost`, R5); the live views' request and the snapshot POST require a custom header, which another site cannot make the browser send without a CORS preflight that the server never answers (the live request because it ends the running computation and starts one: code review, finding 5); every value is put into the page as text, never as HTML (paths and metadata come from users' files); no connection string, password or environment value in a page, a snapshot or a log line (errors of the stores are shown by store name and the library's message, as `modama-chain` does).

What "read-only" rests on (R3): `crawler-db` trusts any connection as `postgres` (`docker-compose.yml`, `POSTGRES_HOST_AUTH_METHOD: trust`) and OpenSearch has no security plugin, so in this stack the only guard against a write is the tool's own code: read-only transactions (`default_transaction_read_only`) and GET requests only. The warehouse database is read with its read-only role. Other local accounts on the shared server can reach ports on 127.0.0.1: the runbook's acceptance of that ("ports on localhost, trusted users") is extended to this tool explicitly (R7); no start token (not asked).

### D15. Dependencies (@weber, 2026-11-12, item 215: "yes go with your lean, sounds sensible")

`xmltodict` 1.0.4 and `jsonschema` 4.26.0 (both the current release on PyPI, checked 2026-11-12), pinned exactly, with jsonschema's dependencies pinned as the warehouse's `uv.lock` (v1.10.0) has them (`attrs`, `jsonschema-specifications`, `referencing`, `rpds-py`), in an extra `browse` of `modama-chain`, installed only in the browse image. MIT each. No `git` (R4).

### D16. Out of sync (@weber, 2026-11-12: "Most importantly, detect when we are out of sync!")

The search API hit (D9) and the matchmaker entry (D10) each declare, next to their code in `upstream.py`, what they follow: upstream's version (the image version in `search-api.Dockerfile`, the commit in `matchmaker.Dockerfile`'s `ADD`) and a SHA-256 over the `*.patch` files of `patches/search-api/` and `patches/matchmaker/`, in name order, contents only. One module, `sync.py`, reads the actual values from those files and compares; the values are nowhere else (the page's "From:" line is formatted from the declaration). Three places use that one comparison: the page (a red line on the view, and in the snapshot; a file that cannot be read is a warning too), `tests/test_sync.py` (fails, never skips, with the declaration to put in after the review), and the e2e test's content comparisons, unchanged. In the container only those files are mounted, read-only, under `/upstream/search-stack/`, not the stack's folder (`staging.env`); single-file mounts keep the content they had at the start, so a change shows after `restart browse`. Not declared: D7's call and D8's loop, which run upstream's own files from the submodules and are compared by the e2e test.

## Risks

- **Version skew:** the live views run the checkout's code, the stored ones what the deployed images ran. That is the point (stored vs live), but a staging checkout ahead of the images shows differences that a re-crawl would bring.
- **Emulations drift** from upstream (D7 call, D8 loop, D9, D10). Mitigation: file and line references in the code and the page; D9 and D10 declare what they follow and are marked when the stack builds something else (D16); the e2e test compares D7, D8 and D9 with what the stack stored; D10 is checked by eye against matchmaker.
- **Large folders:** the live views of a file in a folder of 67,600 files may take a minute or more on NFS (D3); measured by @weber on staging.
- **Code from the checkout on staging** (D4; accepted by @weber, item 216).

## Not now

A search box; the stored DataCite of the last harvest event; the embedding text; rendering matchmaker's real component; a link to matchmaker's results page; recognition of the subfolders and adoption (D5); the trace's lines, the dataset row's other columns and a "copy link" button (R9: no request asks for them; the address bar is the link); git information in snapshots (R4); a start token; the same in `deploy/`.
