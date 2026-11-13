## ADDED Requirements

### Requirement: The browser lists a folder of the data tree
`modama-chain browse` SHALL serve a page that lists the entries of a folder of the data root (name, and whether it is a folder or a symlink), with the path in the page's URL, and SHALL move between entries and folders by keys without leaving the page (design D11). A listing SHALL read the folder's directory entries only, without a `stat` per entry.

#### Scenario: A folder with tens of thousands of files
- **WHEN** a folder holds 70,000 files and its listing is requested
- **THEN** the response names all 70,000 within 2 s in the VM

#### Scenario: A link to a file
- **WHEN** the page is opened with `?path=/notes/readme.txt`
- **THEN** it lists `/notes/` with `readme.txt` selected and shows that file's views

### Requirement: Paths outside the data tree are refused
The browser SHALL refuse, with HTTP 400 and without reading anything, a path that does not start with `/`, that contains a NUL or an empty, `.` or `..` component, or that passes through a symlink, and SHALL never read outside the data root's real path (design D12).

#### Scenario: Going up
- **WHEN** the path is `/notes/../../etc/passwd`, or the same with `%2e%2e` in the query string
- **THEN** the answer is 400 and nothing outside the root is read

#### Scenario: A symlink out of the tree
- **WHEN** `/notes/out` is a symlink to `/etc` and the path is `/notes/out/passwd` or `/notes/out`
- **THEN** the answer is 400

#### Scenario: An absolute path
- **WHEN** the path is `/etc/passwd`, `etc/passwd` or `//etc/passwd`
- **THEN** the answer is 400 or 404 for a path under the root, and nothing outside the root is read

#### Scenario: A NUL
- **WHEN** the query string carries `%00` in the path
- **THEN** the answer is 400

### Requirement: A file's views show the stages, each labelled by its source
For a file, the browser SHALL show the stored dataset holding it and its record as the OAI-PMH server serves it, and the live dataset and record computed by the crawler's code from the checkout, then the DataCite record by the harvester's XSLT, the warehouse's index document, the search API's hit and matchmaker's expanded cited-dataset entry, live and, when indexed, as stored. Each view SHALL be labelled "stored", "actual code" or "emulated", an emulated one with the file and lines it follows (design D6 to D10). An emulation of a service SHALL declare the upstream version and the hash of our patches it follows; where that differs from what the search stack builds, the view and its snapshot SHALL say so, and a unit test SHALL fail (D16).

#### Scenario: A file found everywhere
- **WHEN** a file of the e2e tree has been crawled, harvested and indexed, and its views are requested
- **THEN** every view is present, and the live `<record>` equals the one in the OAI-PMH server's `GetRecord` response

#### Scenario: The live index document matches the stored one
- **WHEN** an EMPAD header of the e2e tree is indexed and unchanged since
- **THEN** the live DataCite equals the warehouse's stored harvest event, the live index document equals OpenSearch's `_source` for its URL apart from `emb`, and the emulated search hit equals the real one apart from the scores

#### Scenario: A file the crawler has not seen
- **WHEN** a file was written after the last crawl
- **THEN** the stored views say it has no dataset, and the live views show its record

#### Scenario: An emulation out of sync
- **WHEN** `matchmaker.Dockerfile` of the search stack names another commit than the matchmaker entry's declaration
- **THEN** the matchmaker entry's view and the snapshot carry "out of sync: emulates matchmaker <declared commit> + patches <hash>, the stack builds <commit> + patches <hash>; review the emulation", the other views carry none, and `test_sync.py` fails with the declaration to put in after the review

### Requirement: An open folder that is a dataset shows the same views
When a folder is open, the browser SHALL show the folder's views as for a file, stored and live, the live ones from the folder's collapse check: the dataset anchored at it or above it when one collapses it (a Zarr store, `.git`, an environment, `node_modules`, a Dask scratch space). A click on a folder SHALL still open it. A folder that no collapsed dataset holds SHALL show its stored views and, live, "a folder: no live views" (@weber, 2026-11-13; design D5, D11).

#### Scenario: An open Zarr store
- **WHEN** the open folder is a Zarr store and its live views are requested
- **THEN** the live dataset is the collapsed one anchored at the store, followed by its record, DataCite, index document, search hit and matchmaker entry

### Requirement: The live views run the checkout's current code
The live views SHALL be computed in a new process for each request, with an environment holding no database, HTTP or Airflow setting, so that an edit to a format, an extractor, `records.py` or `render.py` in the mounted checkout shows on the next request, without a rebuild, a restart or a crawl (design D4).

#### Scenario: An edited description
- **WHEN** the description rule in `records.py` of the checkout is changed between two requests for the same file
- **THEN** the second request's live record shows the new description

### Requirement: Live work is bounded
A live computation SHALL list and recognise only the selected file's folder and the folders above it, SHALL extract only the dataset holding the file, with one worker under the crawler's time limit and memory budget, and SHALL be ended with all its processes after twice the crawler's extraction time limit, the view saying so. For an open folder, it SHALL run only the pre-order calls of the folders down to it and extract only the collapsed dataset holding it (design D3, D5).

#### Scenario: A file next to a large subfolder
- **WHEN** a file's folder has a subfolder of many files, and the file's live views are requested
- **THEN** nothing in the subfolder is listed or read, and only the file's dataset is extracted

#### Scenario: A normal folder
- **WHEN** the open folder holds files, no collapsed dataset holds it, and its live views are requested
- **THEN** no file in it or in the folders above it is read, and the live views say "a folder: no live views"

#### Scenario: A computation over the limit
- **WHEN** a live computation runs longer than its limit
- **THEN** its process group is gone and the view names the limit

### Requirement: Live computations per tab
At most N live computations (`MODAMA_BROWSE_LIVE`, default 4) SHALL run at once across the page's tabs; further ones SHALL wait first in, first out, and the page SHALL show how many wait ahead. A new request of a tab SHALL end that tab's running computation or take its waiting one out of the queue. Requests without a tab id SHALL count as one tab (design D3, decision 301).

#### Scenario: A newer request of the same tab
- **WHEN** a tab's live computation runs and the same tab requests another
- **THEN** the first one's process group is gone, its answer is "ended by a newer request", and the second one's result is shown

#### Scenario: Two tabs
- **WHEN** one tab's live computation runs and another tab requests one
- **THEN** both run and each tab gets its own result

#### Scenario: More requests than slots
- **WHEN** N live computations run and two more tabs request one each
- **THEN** both wait, the first with 0 and the second with 1 ahead, and they run in the order they came as slots free

#### Scenario: A newer request of a waiting tab
- **WHEN** a tab's live request waits in the queue and the same tab requests another
- **THEN** the waiting one leaves the queue at once without starting a process, answered "ended by a newer request", and the newer one waits at the end of the queue

#### Scenario: A request without a tab id
- **WHEN** live computations are requested without the tab header, one while another runs
- **THEN** they count as one tab: the running one is ended by the newer one

### Requirement: The browser writes only snapshots
The browser SHALL write nothing but snapshot files, into its snapshot folder only, and SHALL use read-only database transactions. A snapshot SHALL be one Markdown file holding the path, the path on the server, the time, the extractor identity and every view's content, and SHALL hold no credential (design D13).

#### Scenario: Save for Claude
- **WHEN** the snapshot of a file's views is requested
- **THEN** one new file `<time>-<name>.md` is in the snapshot folder with every view, its name is in the answer, and no value of the environment's passwords or connection strings appears in it

### Requirement: The browser answers only on the local machine
The service SHALL be published on 127.0.0.1 only, SHALL refuse requests whose `Host`, without its port, is not `localhost` or `127.0.0.1`, and SHALL refuse a snapshot request without its custom header (design D14).

#### Scenario: Another host name
- **WHEN** a request carries `Host: evil.example:7655`
- **THEN** the answer is 403

#### Scenario: A cross-site form
- **WHEN** a snapshot is requested by a POST without the header
- **THEN** the answer is 403 and nothing is written

### Requirement: Flagged files are listed as links into the browser
`modama-chain review` SHALL read, read-only, the stored warnings and failed extractions of the whole index and print them on stdout as Markdown (design D17, @weber 354), by kind (`extraction failed`, `two formats want it`, `not inspected`, `read more than 64 KiB`, `over its read limit`, `slow extraction`, `other warnings`), then by format (else `no format named`), each group with its count and its first entries by path, each entry a link into the browser with its text, and one summary line per group on stderr.

#### Scenario: Files two formats want
- **WHEN** the index holds the warning `em/merlin: acq_2.mib is claimed by em/empad; two formats want it` at `/scan/acq.hdr`
- **THEN** stdout has the heading `two formats want it`, under it `em/merlin (1)` and the entry ``[`/scan/acq.hdr`](http://localhost:7655/?path=%2Fscan%2Facq.hdr): em/merlin: acq_2.mib is claimed by em/empad; two formats want it``, stderr has the line `two formats want it, em/merlin: 1`, and the exit status is 0

#### Scenario: A failed extraction
- **WHEN** the extraction of the dataset `/a/b.dm4` by `em/dm4` failed with `OSError(5, 'Input/output error')`
- **THEN** it is listed under `extraction failed`, `em/dm4 (1)`, with that error as its text

#### Scenario: Files not inspected
- **WHEN** the index holds a warning with the marker `not inspected`
- **THEN** it is listed under `not inspected` and under no other kind

#### Scenario: Slow extractions
- **WHEN** (@weber 352, change `slow-extractions`) the dataset `/a/b.dm4` of `em/dm4` carries the warning `em/dm4 extraction took 23.4 s; slow extraction`
- **THEN** stdout has the heading `slow extraction`, under it `em/dm4 (1)` and the entry ``[`/a/b.dm4`](http://localhost:7655/?path=%2Fa%2Fb.dm4): em/dm4 extraction took 23.4 s; slow extraction``, and stderr the line `slow extraction, em/dm4: 1`

#### Scenario: Other warnings, with and without a format
- **WHEN** the index holds `common/text failed: ValueError()` at a folder and `type is ambiguous between a, b; using a` at a file
- **THEN** both are listed under `other warnings`, the first under `common/text`, the second under `no format named`

#### Scenario: A path with brackets and spaces
- **WHEN** a flagged path is `/SI data (20)/a+b #1.dm4`
- **THEN** its link holds the path percent-encoded, brackets included, so that a Markdown link cannot end early (finding F19), and the link's query parameter `path` decodes to that path

#### Scenario: Another address of the browser
- **WHEN** the command runs with `--browse http://localhost:17655/` (staging's tunnel)
- **THEN** every link starts with `http://localhost:17655/?path=`

#### Scenario: Nothing flagged
- **WHEN** the index holds no warning and no failed extraction
- **THEN** stdout says `Nothing flagged.`, stderr `nothing flagged`, and the exit status is 0

#### Scenario: A closed pipe
- **WHEN** the output is piped into `head -1`
- **THEN** the command ends with status 0 and without a traceback

#### Scenario: The database unreachable
- **WHEN** the crawler's database cannot be reached
- **THEN** stderr names the crawler database and the exit status is 2, as for `trace`

### Requirement: The review list can be narrowed
`modama-chain review` SHALL list the first 20 entries of each group, `--limit N` the first N, `--all` every one, with the group's whole count either way; `--marker KIND` SHALL keep the groups of one kind, `--format ID` those of one format, and both together their intersection (design D17).

#### Scenario: More entries than the limit
- **WHEN** a group has 25 entries
- **THEN** the first 20 by path are listed, then the line `- 5 more: --all lists them`; with `--limit 3` the first 3 and `- 22 more: --all lists them`; with `--all` all 25; and the counts say 25 each time

#### Scenario: One kind, one format
- **WHEN** the index holds warnings of two kinds and two formats, and the command runs with `--marker 'two formats want it'`, with `--format em/k2is`, and with both
- **THEN** each run lists only the groups of that kind, of that format, or of both
