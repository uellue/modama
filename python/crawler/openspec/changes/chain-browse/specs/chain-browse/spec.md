## ADDED Requirements

### Requirement: The browser lists a folder of the data tree
`modama-chain browse` SHALL serve a page that lists the entries of a folder of the data root (name, and whether it is a folder), with the folder's path in the page's URL, and SHALL move between entries and folders by keys without leaving the page (design D11). A listing SHALL read the folder's directory entries only, without a `stat` per entry.

#### Scenario: A folder with tens of thousands of files
- **WHEN** a folder holds 70,000 files and its listing is requested
- **THEN** the response names all 70,000 within 2 s in the VM

#### Scenario: A link to a file
- **WHEN** the page is opened with `?path=/notes/readme.txt`
- **THEN** it lists `/notes/` with `readme.txt` selected and shows that file's views

### Requirement: Paths outside the data tree are refused
The browser SHALL refuse, with HTTP 400 and without reading anything, a path that does not start with `/`, that contains a NUL or an empty, `.` or `..` component, or that passes through a symlink, and SHALL never read outside the data root's real path (design D12).

#### Scenario: Going up
- **WHEN** the path is `/notes/../../etc/passwd`
- **THEN** the answer is 400 and nothing outside the root is read

#### Scenario: A symlink out of the tree
- **WHEN** `/notes/out` is a symlink to `/etc` and the path is `/notes/out/passwd` or `/notes/out`
- **THEN** the answer is 400

#### Scenario: An absolute path
- **WHEN** the path is `etc/passwd` or `//etc/passwd`
- **THEN** the answer is 400

### Requirement: A file's views show every stage, each labelled by its source
For a path, the browser SHALL show: the stored dataset holding it and its record as the OAI-PMH server serves it, and the trace; the live dataset and record computed by the crawler's code from the checkout; the DataCite record by the harvester's XSLT; the warehouse's index document, live and as stored in OpenSearch; the search API's hit, live and as `/search` returns it; and matchmaker's expanded cited-dataset entry. Each view SHALL be labelled "stored", "actual code" or "emulated", an emulated one with the file and lines it follows (design D6 to D10).

#### Scenario: A file found everywhere
- **WHEN** a file of the e2e tree has been crawled, harvested and indexed, and its views are requested
- **THEN** every view is present, and the live `<record>` equals the one in the OAI-PMH server's `GetRecord` response

#### Scenario: The live index document matches the stored one
- **WHEN** an EMPAD header of the e2e tree is indexed and unchanged since
- **THEN** the live index document equals OpenSearch's `_source` for its URL, apart from `emb`, and the emulated search hit's computed fields equal the real hit's

#### Scenario: A file the crawler has not seen
- **WHEN** a file was written after the last crawl
- **THEN** the stored views say it has no dataset, and the live views show its record

### Requirement: The live views run the checkout's current code
The live views SHALL be computed in a new process for each request, so that an edit to a format, an extractor or `records.py` in the mounted checkout shows on the next request, without a rebuild, a restart or a crawl (design D4).

#### Scenario: An edited description
- **WHEN** the description rule in `records.py` of the checkout is changed between two requests for the same file
- **THEN** the second request's live record shows the new description

### Requirement: Live work is bounded
At most one live computation SHALL run at a time; a new one SHALL end the running one with all its processes. A live computation SHALL extract with one worker under the crawler's time limit and memory budget, and SHALL be ended with all its processes after twice the crawler's extraction time limit, the view saying so (design D3).

#### Scenario: A computation over the limit
- **WHEN** a live computation runs longer than its limit
- **THEN** its process group is gone and the view names the limit

#### Scenario: A newer request
- **WHEN** a live computation runs and a second one is requested
- **THEN** the first one's process group is gone and the second one's result is shown

### Requirement: The browser writes only snapshots
The browser SHALL write nothing but snapshot files, into its snapshot folder only, and SHALL use read-only database transactions. A snapshot SHALL be one Markdown file holding the path, the path on the server, the time, the checkout's commit and the files changed under `python/`, the extractor identity and every view's content, and SHALL hold no credential (design D13).

#### Scenario: Save for Claude
- **WHEN** the snapshot of a file's views is requested
- **THEN** one new file `<time>-<name>.md` is in the snapshot folder with every view, its name is in the answer, and no value of the environment's passwords or connection strings appears in it

### Requirement: The browser answers only on the local machine
The service SHALL be published on 127.0.0.1 only, SHALL refuse requests whose `Host` is not `localhost` or `127.0.0.1`, and SHALL refuse a snapshot request without its custom header (design D14).

#### Scenario: A cross-site form
- **WHEN** a snapshot is requested by a POST without the header
- **THEN** the answer is 403 and nothing is written
