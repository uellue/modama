# Proposal

## Why

@weber wants to fine-tune metadata extraction and how a record looks in the search's web frontend with a turn-around of seconds, on staging's real data (request of 2026-11-12, verbatim in `design/requirements-pipeline.md`, 2.1, scenario D):

> I'd like to now fine-tune the metadata extraction and the representation in the warehouse UI with very quick turn-around. Can you build me a tool I can run in staging that does the following:
> * Web based file system browsing interface, a bit similar to the browse interface of the mgmt interface. That allows me to navigate the file system tree very quickly without mode change.
> * Shows the OAI-PMH record of a file
> * Shows how it will be shown in the details view of the warehouse web interface. E.g. in the chat interface, when I expand one of the "Datasets cited in this answer" [1] ... entries
>
> ...and a quick way to copy the full storage path on ptycho so that I can mess with that file in e.g. a Jupyter notebook
>
> Please run the actual code that is used along the chain as far as possible, and emulate its behavior where that is not possible or a bad idea. You can just pull them from the original source if that makes your life easier, otherwise import it form the right location and call the actual code from the actual project, so that we don't have to keep our copy in sync all the time.

and, the same day, "...and a way for me to reference it here so that we can chat about it and improve" ("here": the Claude Code chat, which reads the shared checkout but cannot reach staging).

Today the only way is a crawl (hours on staging), a harvest and an indexing run, then a search and a chat question in matchmaker; `modama-crawler records PATH` shows the live oai_dc record of a directory but nothing after it, and needs a shell in the container.

## What Changes

- **`modama-chain browse`**, a read-only web tool in `python/search-chain/` (package `modama-chain`): a folder listing on the left, the selected file's views on the right, keys to move, open and go up, the path in the URL. For a file, side by side and each labelled "stored", "actual code" or "emulated":
  - stored: the crawler's dataset holding it and its record, as the OAI-PMH server serves it, and `modama-chain trace`;
  - live, with the code of the checkout: recognition and extraction by the crawler and the format collections, `records.build`, rendered as the server renders it; then the harvester's DataCite conversion (upstream's XSLT), the warehouse's transformation to its index document (upstream's own functions), the search API's hit and matchmaker's expanded "Datasets cited in this answer" entry (both emulated from their source);
  - the stored index document from OpenSearch and the real search API hit, when the record is indexed;
  - a copy button for the file's path on the server (ptycho: `/storage/er-c-data/…`), one for the view's link, and "Save for Claude", which writes all views of the file as one Markdown file into the checkout's `.claude/field-tests/browse/` and shows its short name to copy.
- An edit to an extractor, a recognizer or `records.py` shows on the next reload of the page: the live part runs in a fresh process per file. Other edits (this tool, `render.py`) need `docker compose restart browse`, seconds.
- **A service `browse`** in the search stack: on 127.0.0.1 only (test 7655, staging 17655), the sources mounted read-only from the checkout, the data tree read-only as `STAGING_USER` on staging, the owners' names through sssd. It writes only the snapshots.
- **The crawler's walk takes a `top` directory** (`walk(root, formats, top=…)`): the pre-order calls of the directories above it and the walk of its subtree, with paths relative to the data root, so that the tool recognises one folder as the crawl does, with the crawler's own code. A crawl is unchanged.
- Requirement scenario D in `design/requirements-pipeline.md`; the stack's README ("Looking around"), the runbook (staging commands), `modama-chain`'s README.

Behaviour towards the user: a new subcommand `modama-chain browse` and a new service `browse` in the test stack and on staging (a page on 127.0.0.1:7655, staging 17655, reached by an SSH tunnel). Nothing changes for a crawl, the records, the harvest, the index or the search; the walk's new parameter is not used by the crawl. `runtest.sh` checks one more service; the e2e test checks the browser's live record against the OAI-PMH server's.

Out of scope: editing anything through the tool; a search box or a view of the warehouse's records other than by path; the chat itself (the answer's text, the model); logos, the Data Player and the citation export of matchmaker's entry; the embedding vector and the ranking (no embedding model in the tool); access per user (BACKLOG, "Per-user views"); production (`deploy/`).

Serves: @weber's requests of 2026-11-12 (scenario D); requirements-pipeline 1.3 (admin and agent time per iteration), 2.4 "The operator stays in control" (the tool shows what each stage makes of a file, by the stage's code); R25/R32 (the Dublin Core mapping is what is being tuned).

## Capabilities

### New Capabilities
- `chain-browse`: browsing the data tree read-only with every stage's view of a file, stored and live, and snapshots of them.

### Modified Capabilities
- `crawl`: the walk of a subtree recognises it as the crawl of the whole tree does.

## Impact

- `python/search-chain/`: `src/modama_chain/browse.py` (web app), `views.py` (the views of a path), `live.py` (the crawler part, run as a child process), `upstream.py` (harvester, warehouse, search API, matchmaker), small additions to `crawler.py` and `warehouse.py`; `cli.py` (`browse`); tests; README; `pyproject.toml` (extra `browse`).
- `python/crawler/`: `src/modama_crawler/walk.py` (`top`), `tests/test_walk.py`, the `crawl` spec, `BACKLOG.md`, `design/requirements-pipeline.md`, `design/field-tests/search-stack-staging-runbook.md`.
- `prototypes/search-stack/`: `docker-compose.yml`, `docker-compose.override.yml`, `docker-compose.staging.yml` (service `browse`), `browse.Dockerfile` (new), `runtest.sh`, `test_e2e.py`, `README.md`.
- New dependencies (to be confirmed, design "Dependencies"): `xmltodict` 1.0.4 and `jsonschema` 4.26.0, pinned to the warehouse's transform environment (its `uv.lock` of v1.10.0), in the extra `browse` of `modama-chain` only; the Debian package `git` in the browse image. No new JavaScript or CSS library.
