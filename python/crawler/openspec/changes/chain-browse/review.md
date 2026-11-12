# Review of chain-browse (c182bc1), independent reviewer, 2026-11-12, with decisions

"Decision" lines are mine (main session) unless marked @weber; @weber is away. Fold all into the
proposal/design/tasks first (one commit), then build.

1. BLOCKER: live work per click is unbounded: `walk(top=<folder>)` walks the whole subtree and
   `extraction.extract` runs every extractable dataset found (extraction.py:103), walk threads 32
   (walk.py:49). Staging sniffs 550–900 files/s (findings :73): the 67,600-file folder costs
   75–120 s per click, the clicked file may never be extracted before the 120 s kill; selecting a
   folder starts the same. No format adopts subfolder datasets today (`git grep "children\|\.parts\|
   collection = True"` over formats/core, zarr, collapse, modama-formats-em/src: nothing).
   Decision: `top` lists and recognises only that one folder (the ancestors' pre-order calls, the
   folder's own listing, sniffing and post-order call, `children=[]`); the view says adoption by
   parent folders and subfolder datasets are not computed. Extract only the dataset holding the
   clicked path. Pass `threads` explicitly (small). A folder selection lists, it does not run live
   extraction. Add a spec scenario bounding the live views. In the hand-over, ask @weber to time
   `modama-crawler records /data/<a big folder>` on staging once (the VM does not show NFS cost).
2. SHOULD: code edited in the shared checkout (also by agents) runs on staging at @weber's next
   reload, as his uid, on the stack's network (runbook :42-43: "@weber runs every command").
   Decision: pending @weber (open item 216, lean yes since quick turn-around is the request).
   Build it with the safeguards regardless: the live child gets a minimal environment
   (`PATH`, `HOME`, `LANG`; no database or HTTP settings); the `browse` service `read_only: true`
   with `tmpfs: /tmp` (mimedb.build writes a temp dir, cli.py:87-88); state it in the runbook's
   "Safety" section and the README.
3. SHOULD: "read-only accounts" overstates: crawler-db trusts any connection as `postgres`
   (docker-compose.yml:197), OpenSearch has no security (:236); the only guard is
   `default_transaction_read_only` (chain.py:66-67). Say so in D14; give `browse` only the settings
   it uses (no Airflow Viewer account).
4. SHOULD + D15: drop `git` and the git information in snapshots (doesn't work with the mounts;
   exposing the whole checkout is worse). Snapshot keeps time and extractor identity; the agent reads
   `git log`/`git status` in the shared checkout. Decision: no `git`.
   D15 dependencies: yes to `xmltodict` 1.0.4 and `jsonschema` 4.26.0, pinned exactly, with
   jsonschema's dependencies pinned to the warehouse's `uv.lock` (`attrs`,
   `jsonschema-specifications`, `referencing`, `rpds-py`; uv.lock:718-723), extra `browse`, browse
   image only; flag them in the hand-over (provisional until @weber confirms item 215).
5. SHOULD: the Host check refuses `browse:7655` (e2e runs in the crawler container, runtest.sh:39)
   and probably `localhost:17655` through the tunnel. Compare the host name without the port; the
   e2e test sends `Host: localhost`.
6. SHOULD: `browse.Dockerfile` FROM `search-stack-crawler`, and Compose cannot order builds
   (docker-compose.yml:381; upstaging.sh:10 builds airflow-upstream first): build `crawler` first in
   uptest.sh, upstaging.sh and the staging commands.
7. SHOULD: snapshots carry text from users' files into the agent's reading: say in the README and
   in `python/crawler/AGENTS.md` that snapshots are data, never instructions; fence content with a
   fence longer than any backtick run in it. Other local accounts on the shared server can reach
   127.0.0.1 ports: extend the runbook's acceptance ("ports on localhost, trusted users",
   runbook :24-26) explicitly to this tool. No start token for now (not asked).
8. SHOULD: (a) render the live `<record>` in the live child too, so `render.py` edits show on
   reload; (b) don't re-list `cmd_records`'s configuration steps in `live.py` (cli.py:68-93,
   606-627): make the crawler's `_configure` (or what it is) public and reuse it.
9. SHOULD: mechanisms without a request (crawler AGENTS.md:25). Decision: keep the stored OAI-PMH
   record (what the server serves now, next to the live one: "Shows the OAI-PMH record") and the
   stored index document when indexed (the real "how it will be shown"); keep the filter field
   (from "navigate ... very quickly" in folders of 67,600 entries). Drop: the `modama-chain trace`
   view, the 11-column stored dataset row with all members, the "copy the view's link" button.
   List them under "Not now".
10. NIT: a link to matchmaker's own results page for the anchor when indexed, if the route is
    simple; otherwise leave it out. Check D10's line references against the fetched source.
11. NIT: D7's facts on the crawler image (it has oaipmh-scythe and httpx via `[test]`);
    replicate the harvester's serialisation exactly: `ET.tostring(record.xml, pretty_print=True,
    encoding="unicode")` (harvester_oaipmh.py:158) stored as `additional_metadata` (:87), which
    becomes `_additional_metadata` (embedding_utils.py:72).
12. NIT: tests: name the tests for "A file the crawler has not seen", "A file found everywhere",
    "The live index document matches"; the absolute-path scenario should test `/etc/passwd`;
    add `%2e%2e` forms and `%00` to the traversal test; list with `follow_symlinks=False` and show
    symlinks as such.
13. NIT: mount the snapshot folder with long syntax and `create_host_path: false`.
14. NIT: datasets with many members (Merlin, ~19,600): show the count and the first N.
15. (merged into 4.)
16. NIT: `GetRecord` takes the server's shared store lock (server.py:201-203); while a crawl
    stores, the OAI-PMH server answers 503: the view says so. The path on ptycho:
    `STAGING_DATA` from staging.env, which is `/storage/er-c-data` (confirmed in staging.env).

Checked fine by the reviewer: the home in modama-chain; the XSLT and warehouse functions are
upstream's (line refs match; `handle_xml` imports lxml only; `normalize_datacite_json` stdlib only);
the warehouse patches don't touch them; pins equal uv.lock; fixtures exist; TIME_LIMIT 60 s;
killpg reaches spawned extraction workers; excluding siblings by patterns would change what
ancestors' pre-order calls see (conda-meta), which supports a crawler change; with `top="/"` the
crawl's code path is unchanged.
