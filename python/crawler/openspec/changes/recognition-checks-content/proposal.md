# Proposal: recognition checks the content

Renamed from `extractor-rejects-type` (decision 168, 2026-11-12); the branch keeps its name, `worktree-agent-acfa97ac4ec4925f5`. Revised on 2026-11-12 with the review (`review.md`) and @weber's decisions 172 to 174.

## In short

A file whose name says one type but whose content says another should not be published under the name's type. Example: a text file `notes.gtg` is published today as "Gatan Digital Micrograph .gtg tag file", because the name `*.gtg` decides without the file being read.

With this change, the format that knows the type checks the file's first bytes while it recognises the directory, and can say "this file is not of my type". The file then gets the type it would have had without that name rule, in the same pass: `notes.gtg` becomes a plain text file, with no warning. The reason ("em/k2is: not application/x.dm-gtg, no DM header") shows in `records --verbose` and in `modama-chain trace`.

What is broken stays broken (@weber, 2026-11-12, decision 172: "This scenario is, in fact, a broken K2IS"). A `Capture7_.gtg` that an interrupted copy left empty, next to its 8 sector files `Capture7_1.bin` to `Capture7_8.bin`, is one K2IS capture whose extraction fails, as today. K2IS checks the header only of a `.gtg` that has no sector files of its stem.

`.dmw` files are claimed (decision 173). A workspace `exemplary_workspace.dmw` with a Digital Micrograph header becomes a dataset of the new format `em/dmw`, "Gatan Digital Micrograph workspace", described by every tag it holds: the names and window positions of the images it opens. A DM3 `.dmw` is handled the same way and marked as a file of interest (decision 174), since none has been seen yet. A text or empty `.dmw` becomes a plain text file. A compressed workspace `exemplary_workspace.dmwx`, a ZIP of the workspace and its images, becomes a dataset of `em/dmwx`, described by its workspace's tags and its members, without reading the images (decision 190).

A file typed by its content, not by its name, keeps its type. Nothing new is stored.

## Why

A file that only one name rule matches is typed by its name alone. Detection returns before it reads the file (`mime.py:177-184`). Since `dm-containers-and-k2is` (merged into `crawler`), a text or empty `notes.gtg` or `x.dmw` is therefore described as a Gatan file (that change's review, finding 1). That is a false statement to a searcher, the problem staging finding F15 set out to fix. The review proposed giving these names a second rule (the globs on `application/octet-stream`), so that the content always decides. @weber prefers that the format says "this is not, in fact, a Gatan gtg file". This works for name collisions nobody knows about yet, and the name keeps its fast match for every other format.

The first version of this change rejected the file at extraction. @weber's follow-up (2026-11-12, question 149, "149 sounds sensible!"): decide it during recognition. Recognition can already read a file's first bytes (`Directory.read`, `formats/__init__.py:175-184`, 1 MiB per format call), and EMPAD uses that in its `recognize`. What is missing is a way for a format to say, while recognising, "this file is not of the type its name gave it".

The 2,036 `.dmw` files on staging (F15) are single files without a description today. @weber (173): "We claim it. … We just include everything, and keep a TODO to filter for relevant tags."

Serves R25 (honest types), R30 (records that don't mislead a searcher), R23/R8 (a failure stays a reported failure), R10 (a re-crawl does no work for an unchanged file).

## What Changes

- While recognising a directory, a format can say that one of its files is **not of the type the file's name gave it**, with a reason.
- **Only a file typed by its name alone qualifies**: exactly one best name rule gave it the type. Its type becomes what detection gives without that rule: another name rule, else the content, else `text/plain` or `application/octet-stream`. This takes effect at once, for the formats that run after it in the same directory and for the file as a single file. A format for the new type can claim it if it runs later.
- A format that drops types must run before the formats that are to claim its files' new types. The format's priority says that. When a format that ran earlier on the directory reacts to a dropped file's new type, the crawl warns: the order is wrong.
- A file typed by its content keeps its type. The crawl warns, naming the format and the reason: a content match that a format contradicts points at a weak content rule (decision 145, flow F). So does a file a format that ran earlier has claimed.
- A file that cannot be read while it is checked keeps its type, the crawl warns at it, the rest of the directory's result stands, and the directory is recognised again next crawl (code review finding 1; revised from "reported as the format's failure").
- The reason goes into the **basis** of the dataset that holds the file ("single file; em/k2is: not application/x.dm-gtg, no DM header"). `records --verbose` shows it, also for a single file, and the crawler line of `modama-chain trace` shows every dataset's basis. No warning, and no count in the crawl report (decision 148).
- **Nothing new is stored.** The type and basis are stored with the dataset as they are today. An unchanged directory keeps them on the next crawl without reading a file. A changed file is checked again.
- **In `modama-formats-em`**, built here on `crawler` (where `dm-containers-and-k2is` is merged):
  - `em/dmw` claims each `.dmw` with a DM3 or DM4 header as a dataset of one file and extracts every tag. A DM3 one gets the note "file of interest" in its basis. A `.dmw` without the header loses the name's type.
  - K2IS groups a `.gtg` with 8 sector files of its stem whatever the `.gtg` holds. It checks the header only of a `.gtg` without sector files of its stem, and drops the type of one without a DM header; a DM3 one is kept and flagged as a file of interest (decision 183).
  - Both run at priority 61, before the DM3 and DM4 formats (decision 165).

Behaviour towards the user:
- A searcher or harvester sees a stray `notes.gtg` or `notes.dmw` holding text as `dc:format` `text/plain`, described as a plain text document. An empty `empty.dmw` or `empty.gtg` becomes `text/plain`, as an empty file without a name rule is today. Their datestamps move once.
- A `.dmw` with a Digital Micrograph header, such as `exemplary_workspace.dmw`, gets a record of type `application/x.dm-dmw` whose description lists every tag of the file (the image names as Windows paths, the window positions, the workspace's name), with the subject "Gatan Digital Micrograph workspace". Its datestamp moves once. The images it names stay records of their own (decision 189).
- A `.dmwx` whose first member is a `.dmw` gets a record of type `application/x.dm-dmwx`, "Gatan Digital Micrograph workspace (compressed)", whose description lists the inner workspace's tags and each member with its size. Today it is a single file of type `application/zip` (by content) without a description beyond its size.
- An empty `Capture7_.gtg` next to its 8 sector files stays one K2IS record with a reported extraction failure, as today. So does a broken `scan_2_.gtg` with its 8 sector files next to a complete `scan_.gtg` capture: two K2IS records, and only `scan_2_.gtg`'s extraction fails.
- An admin sees the reason in `records --verbose` (a comment before that file's record) and in `modama-chain trace` (the crawler line's basis). A DM3 `.dmw` shows "file of interest" there. The crawl report has no new count; it has a new warning only for a broken format order or a content-typed file a format contradicts.
- No schema change, and no database recreation.

Out of scope:
- Rejecting files typed by their content.
- Checking the fallback type again: one drop per file per crawl.
- Calling formats that already ran on a directory again after a drop (the order warning reports it instead).
- A count of rejections in the crawl report.
- Filtering the `.dmw` description to the relevant tags (backlog TODO).
- Raising read errors in the walk's own detection (the existing gap of review finding 4, second paragraph; backlog).
- Generic extractors on subtypes (Q15).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `recognition`: a format can say that a file is not of the type its name gave it. The file then gets the type detection gives without it, at once. A file typed by its content, or claimed earlier, keeps its type, with a warning. A broken format order is warned about. A failed or over-budget format call leaves every type and basis as it was, and its warnings go with it. A read error on one file keeps that file's type and leaves the rest of the result. The core's detection of a new type is not charged to the format's byte budget (decision 166).
- `mime-database`: detection can leave a type out.
- `records-cli`: a single file whose name type a format dropped gets a recognition comment with its basis.
- `chain-trace`: the crawler line shows the basis of the dataset that holds the item.
- `formats/dm`: `.dmw` files are claimed and described by their tags; one without a DM header is not a `.dmw` file. `.dmwx` files whose first member is a `.dmw` are claimed and described by that workspace's tags and their members.
- `formats/k2is`: a lone `.gtg` without the DM4 header is not a tag file; a broken `.gtg` with its 8 sector files is a broken capture.

Archive order: after `parallel-walk` (its requirement "A byte budget bounds every format call" is modified here) and `dm-containers-and-k2is` (its capabilities `formats/dm` and `formats/k2is` are modified here).

## Impact

- Crawler:
  - `formats/__init__.py`: `Directory.not_of_type`; `run_post` reading the entries' current types, the order warning, the notes in the basis; `_call` putting types and notes back.
  - `mime.py`: `by_name`, the type a name alone gives, and detection with a type left out, raising read errors when asked.
  - `cli.py`: the `records` comment for a single file with a note.
  - Docs: `formats/TEMPLATE.md`, `README.md` (Walk and recognise), `BACKLOG.md`.
- `python/search-chain`: the trace's crawler line reads `datasets.basis`. Its README, "What it reads", says so.
- `modama-formats-em`: the formats `em/dmw` and `em/dmwx` (with the type `application/x.dm-dmwx` in `dm.xml`) with their extractors in `dm/`, @weber's real workspace as the `.dmw` fixture, the tag walker shared by `dm/` and `k2is/`, the lone-`.gtg` check in K2IS, priority 61 for both, fixtures and their provenance, the comments in `dm.xml` and `k2is.xml`, the README.
- `dm-containers-and-k2is`: its open task 4.1 (review finding 1) points here for the outcome.
- No new dependency (the DM tags are read with RosettaSciIO's reader, already a dependency; not ncempy, design E1). No schema change.

## Decisions by @weber, 2026-11-12 (questions 144 to 149 and 165 to 174, answered on the open-items page)

- **144, where the `em` part goes:** "yes let's group the changes together". Since then `dm-containers-and-k2is` is merged into `crawler`, so the em part is built in this change, on `crawler`, with spec deltas for `formats/dm` and `formats/k2is`.
- **145, files typed by their content:** they do not fall back (flow F in design.md). A format that says such a file is not of its type gets a warning, not a new type.
- **146, the fallback type's own extractor:** resolved by 149. The new type is set during recognition, so a format of that type that runs later claims the file, and its extractor runs as for any of its files. The order rule is in design.md, D3.
- **147, the DM3 header:** "that depends on what we find in the wild. DMW should/could also exist as DM3, I think." @weber makes fresh `.dmw` files with a current GMS (his TODO, open item 155). For `.dmw`, 174 settles it, and for a lone `.gtg` 183: both accept DM3 as a file of interest.
- **148, showing rejections:** "a normal rejection is business as usual. It should go into the per-item tracing / observability". So: no count in the crawl report, and no warning. The reason is in the dataset's basis, shown by `records --verbose` (spec `records-cli`) and by `modama-chain trace` (spec `chain-trace`).
- **149, check during recognition instead of at extraction:** "149 sounds sensible!" This revision of the change.
- **D2's case of the first version** (a single file in a subdirectory that a collection format adopted as a part): "Let's go with your lean until we find a specific example where that is wrong". It holds without a rule of its own. The subdirectory is recognised before its parent, so the file already has its new type when the parent adopts it.
- **165, the order rule:** "yes, go with your lean please!": a format that drops types runs before the formats its files fall back to (`em/dmw` and K2IS at priority 61, D3).
- **166, the re-detection and the read budget:** "yes, please change. First we make it work, and we fix the 'big ticket items'. This sounds like a keyhole case where we focus on it working correctly. We fix when it shows up as a real world drain in monitoring or benchmarking." Read as: the re-detection is not charged to the format's 1 MiB budget (the alternative), so a folder of many misnamed files cannot push a format over its budget and put every type back; its reads are the walk's ordinary reads.
- **167, the trace shows every dataset's basis:** "Yes, longer line is OK. we adjust when we encounter it in the real world."
- **168, the name:** "user facing yes, but we don't need to muck with branch names as long as we know what is what." The change is renamed `recognition-checks-content` (its directory and title, what people read); the branch keeps its name.
- **172 (review finding 1):** "This scenario is, in fact, a broken K2IS." An empty or broken `Capture7_.gtg` next to its 8 sector files is one K2IS dataset whose extraction fails, not 9 single records. K2IS groups by the 8 sectors whatever the tag file holds, and checks the header only of a `.gtg` without its sectors. This also resolves review finding 3.
- **173 (review finding 2):** "We claim it. Can we use ncempy to extract allTags? We just include everything, and keep a TODO to filter for relevant tags." `em/dmw` claims a `.dmw` with a valid header and extracts every tag, values as the reader gives them. The tags come from RosettaSciIO's reader, as K2IS reads them, not from ncempy (design E1, why). The TODO is in the backlog.
- **174 (review finding 5):** "yes, let's just try to handle and perhaps flag this as a 'file of interest' in case we encounter it?" The `.dmw` check accepts DM3 and DM4. A DM3 `.dmw` is claimed and extracted like a DM4 one, and its basis says it is a file of interest; it is the first concrete case of the backlog item "Suspicious results for manual follow-up".
- **183 (a lone DM3 `.gtg`, code review finding 2):** "accept, but flag as a 'file of interest' to be reviewed manually." It keeps the `.gtg` type, with "file of interest: DM3 .gtg, review by hand" in its basis (design E2).
- **184 (the name):** Gatan calls these files "Workspace": keep "Gatan Digital Micrograph workspace". @weber made real workspaces with GMS on 2026-11-12: "The dmw file you can copy, just not the DM files with actual data in them." One is the `.dmw` fixture; nothing of the images or of the `.dmwx` is copied.
- **189 (a workspace and its images):** "a for now, b as backlog": a `.dmw` stays its own dataset whose description names the files; grouping it with its images is a backlog item.
- **190 (the compressed workspace):** "yes, go with your leans": `.dmwx` is added here (design E4).
- Also from @weber, for later (backlog, "Suspicious results for manual follow-up"): "it would be good to be able to scan a real world crawl result for 'suspicious' results. Maybe the crawling, recognition and extraction logic could tag 'interesting' results for manual follow-up?"
