# Design

## Context

See proposal.md, Why. The current state, with line numbers on `crawler` at 50533f9 (the DM and K2IS code of `dm-containers-and-k2is` is merged there):

- `mime.detect_with_tie` returns at once when one name rule is best (`mime.py:177-184`). The content is read only when no name rule matches or several tie (`mime.py:186-213`). It reads `Mime.magic.maxlen` bytes, 18,730 with all installed collections. A read error gives `application/octet-stream` (or the tie's resolution) without raising (`mime.py:187-197`, review finding 4).
- A format reads through `Directory.read(entry, n)`, within a byte budget of 1 MiB per format call (`formats/__init__.py:175-184`, `BYTE_BUDGET` at 235). The read is refused for an entry object that is not the directory's current one (`formats/__init__.py:177-178`).
- `run_post` runs the formats in `ordered` order: priority descending, then format id (`formats/__init__.py:238-239`). It computes the types present, which decide whether a format reacting to types is called, once before the loop (`formats/__init__.py:304`). It takes the types of unclaimed files from the same snapshot (`formats/__init__.py:305, 366-380`). `_call` turns an exception or an over-budget read into a warning and discards that format's datasets for the directory; an `OSError` also sets `Directory.retry`, so the directory is recognised again next crawl (`formats/__init__.py:242-259`).
- `_fill` gives a format's dataset the format's type (`formats/__init__.py:262-274`). An unclaimed file becomes a single-file dataset of its detected type with basis `single file` (`formats/__init__.py:366-380`).
- Type and basis are stored per dataset (`store.py`, table `datasets`). An unchanged directory is taken over with its stored datasets, and no file of it is read (`walk.py:264-265, 296-303`). "Unchanged" means the same listing digest: names, kinds, sizes, owners and times of the entries (`walk.py:91-97`), under the same rule set. The rule set's fingerprint covers the enabled format ids and recognition versions, the distribution versions and the MIME definitions (`selection.py:138-165`).
- `dc:format` and the description's type come from `dataset.type` (`records.py:82`).
- In `modama-formats-em`: `.dmw` and `.gtg` have globs of their own types, `application/x.dm-dmw` (`dm/dm.xml`) and `application/x.dm-gtg` (`k2is/k2is.xml`). The DM3 and DM4 formats `em/dm3` and `em/dm4` have priority 60 (`dm/__init__.py:72`), and so has K2IS `em/k2is` (`k2is/__init__.py:225`). K2IS reacts to the `.gtg` and sector types and groups a `.gtg` with 8 sector files of its stem, the longest stem first (`k2is/__init__.py:230-265`). Nothing claims a `.dmw` or a lone `.gtg`. K2IS's extractor reads the `.gtg`'s tags with RosettaSciIO's `DigitalMicrographReader` on our own handle (`dm.parsed`).

## Goals / Non-Goals

**Goals:**
- A file's record does not claim a type its content contradicts, where the format of that type can tell. The name still decides at no cost for every other format.
- "Not of this type" is kept apart from "of this type, but broken". A file is broken when the other files around it say what it is (a `.gtg` next to its 8 sector files, decision 172); it is not of the type when nothing but its name says so.
- `.dmw` files are described by their tags (decision 173).
- The same data gives the same result on every crawl, with nothing new stored.

**Non-Goals:**
- A check of files typed by their content.
- Calling a format again after a later format changed a type.
- Rejection at extraction.

## Decisions

**D1. `Directory.not_of_type(entry, reason) -> Entry`, during the post-order call.** A format calls it while recognising, after reading the file's first bytes through `d.read`, for example `d.not_of_type(e, "no DM header")`. The core then does the following:
- It checks that the type came from the name alone, by D2. Otherwise the type stays and the call is answered by D2's warning, without a read.
- It detects the type again without the dropped one: `mime.detect_with_tie(entry.path, exclude=frozenset({entry.mime}), strict=True)`. This follows the checking order unchanged and leaves the excluded type out of the name candidates (the best weight and length are taken among the rest). A sniffed result equal to it counts as no match. So the result is another name rule if one remains, else the content, else `text/plain` or `application/octet-stream` (spec `mime-database`, "Detection can leave a type out"). A tie among the rest is warned about as the walk warns about one. Matching runs in the calling thread: the walk's matching processes are not passed to formats, and drops are rare.
- That read is not charged to the format call's budget (decision 166: make it work correctly first, fix it if monitoring or a benchmark shows it as a real drain): it is the read the walk makes for any file whose type its name doesn't decide, up to `Mime.magic.maxlen` bytes. So a folder of many misnamed files cannot push a format over its budget and put every type back. The format's own reads through `Directory.read` stay charged. The bound: D2 lets each file drop once per recognition, so a directory's uncharged reads are at most one detection read per file typed by its name.
- `strict=True` makes a read error raise `OSError` instead of giving `application/octet-stream` (review finding 4). `not_of_type` catches it and calls `Directory.cannot_read(entry, error)`: the file keeps its type, the crawl warns at the file ("`<format>: cannot read <file>: <error>; type kept`"), and `Directory.retry` is set, so the directory is recognised again next crawl. The format's call goes on and is not discarded, so one unreadable stray file does not take the captures or `.dmw` datasets next to it apart (code review finding 1; @weber's rules: the same data gives the same result or a failure, a failure is retried by the next regular crawl, decision 185, and a transient error must not change good results). The first version of this revision raised the error out of the call, which discarded all of the format's datasets of the directory for that crawl. A format's own read of a file's first bytes is handled the same way where one file's error must not decide the others' outcome: `em/dmw` and K2IS read the header through `dm.header`, which calls `cannot_read`. Without `strict`, detection is unchanged; the walk's own detection keeps its behaviour (out of scope, backlog).
- It replaces the entry in the directory's entries and name index with `replace(entry, mime=new)` and returns the new entry. The old entry object is refused by `d.read` from then on, as an entry of another directory is.
- It keeps a note for the file: format id, dropped type, reason. D4 says where the note goes.

The call is refused with `ValueError` in the pre-order call, where entries have no type, and for an entry of another directory, as `d.read` refuses one.

A format's output is now its datasets, its warnings and its drops (the replaced entries and their notes). `Directory.warn` already works by side effect, so this does not block running formats in worker processes later (architecture G); a worker would return the replaced entries and the notes beside the datasets and warnings (review finding 12).

*Alternative:* a separate stage before recognition, a second method such as `Format.not_of_type(d) -> Iterable[(entry, reason)]` that the core calls on every format before any `recognize`. This is closer to @weber's first framing, "a stage where the extractor is asked 'do you accept this file'". It needs no order rule (D3), since every drop happens before any format recognises, and its output is plain data by construction. *Against it:* a second method for every format author, and a second call per format and directory. K2IS would read each lone tag file's header in one method and group in the other. D1 is what question 149 put to @weber and what he accepted. The alternative is the fallback if the order rule turns out to be a trap.
*Strongest argument against D1:* the result depends on format order (D3).

**D2. Which files: typed by their name alone.** The core recomputes whether the entry's type is the one best name rule's: `mime.by_name(name) -> str | None`, factored out of `detect_with_tie` (`mime.py:177-184`) with no change of result. It is a pure function of the name and the active MIME database, so there is no new field on `Entry`.

If `by_name(entry.name) != entry.mime`, the type stays. That covers a file typed by its content, by a tie the content decided, or by an earlier drop. The directory then gets the warning "`<format>: <file> is not <type> (<reason>), but that type does not come from its name alone; type kept`". This follows decision 145: a content match is positive evidence. When a format contradicts it, the content rule is too weak and is to be fixed with its example (flow F). So it is reported, not hidden.

A file's type is therefore dropped at most once per crawl, and the fallback type is not checked again: one step, no chains. A second call on the same file reads nothing and gives that warning.

Grouped datasets need no rule of their own. A format that groups files decides what is broken before it groups: K2IS groups a `.gtg` with its 8 sector files whatever the `.gtg` holds, so such a group's failure stays an extraction failure, as today (flow B).

**D3. When the new type takes effect: at once, for the formats that run after.** `run_post` recomputes the types present from the directory's current entries before each format. It builds the single-file datasets from the current entries after the last format. A format that ran before the drop is not called again.

So the order rule: **a format that drops types SHALL have a higher priority than the formats expected to claim its files' new types** (review finding 6: "every format of a type its files may fall back to" cannot be met, since a dropped file can take any type its content matches). Equal priorities sort by format id, and `em/dm3` < `em/dm4` < `em/dmw` < `em/k2is`. At 60, a lone DM3 `.gtg` would fall back to `application/x.dm3` after `em/dm3` had run, and stay an unclaimed single file. Hence priority 61 for `em/dmw` and `em/k2is` (E1, E2). TEMPLATE states the rule.

A broken order is reported, not silent (review finding 6): after each format call, for each file the call dropped, `run_post` warns when a format earlier in the order reacts to the file's new type: "`<earlier> runs before <format> and did not see <file> as <new type>`". It is a bug in the formats' priorities, to be fixed there; a normal drop gives no warning (decision 148). Formats that react to every directory (`DIRECTORY`) are not checked: they do not say which types they want. TEMPLATE says so.

A format call that fails or exceeds its budget leaves every type as it was. `_call` keeps the entries, the notes and the number of warnings as they were before the call, and puts them back when it discards the call's datasets (review finding 8; code review findings 6 and 8: the call's own warnings, such as a "type kept" or a tie, go with its result, and only the warning that it failed or was skipped stays). Otherwise a format's half-finished work would change other formats' input while its own result is thrown away. A read error on one file is not a failed call (D1).

A drop of a file that a format which ran earlier has already claimed is undone: the file keeps its type, the claiming dataset its basis, and the crawl warns at the file "`<format>: <file> is claimed by <earlier>; type kept`" (code review finding 4). No installed format does this: `em/dmw` and K2IS drop only files of their own types, which no other format claims.

**D4. What the record and the diagnostics show.** The record shows the new type: `dc:format` and the description's type name come from it. The note goes into the basis of the dataset whose members include the file, appended as `"; <format>: not <type>, <reason>"`:
- a single file: `single file; em/k2is: not application/x.dm-gtg, no DM header`;
- a dataset a later format made of it: `<that format's basis>; test/tags: not application/x.test-tags, no TAGS header` (spec `recognition`, the core's test formats).

`records --verbose` already comments every dataset a format produced with its type and basis (`cli.py:548-551`). A single file now gets a comment too when its basis is not plain `single file`. It is still counted among the single files in the closing comment. `modama-chain trace` shows the basis of the dataset holding the item on its crawler line, for every dataset: one rule, and the basis is the crawler's per-item "why" (decision 167). There is no warning, and the crawl report has no count (decision 148).
*Alternative:* a field of its own on `Dataset` and a column. Clearer to query, but a schema change for a note that the two per-item tools can show from the basis.

**D5. What is stored, and the next crawl: nothing new.** The type and the basis go into `datasets` as for any dataset. There is no `extract_rejected` column, no schema change and no database recreation.
- A crawl of an unchanged directory under the same rules takes over the stored datasets with their type and basis. No file is read and no format is called (`walk.py:302-303`).
- A changed file changes the listing digest, so the directory is recognised again and the format checks again. If the file now has the header, it gets its name type back.
- A new or changed checking format changes the rule-set fingerprint by its id and version, or its distribution's version. Every directory is then recognised again once. The new format id `em/dmw` does that by itself.

So the result is a function of the listing, the files' first bytes and the rules, as recognition is today: the same data gives the same result.

**D6. What the first version needed only for rejection at extraction is removed:**
- The exception `NotOfType` and `Extraction.rejected`.
- The column `extract_rejected`, with the schema change and the database recreation.
- The second detection in the parent after the extraction pool, and the rule for keeping a taken-over type there.
- The format `em/gtg`, and the grouping function that K2IS and `em/gtg` would have shared.
- The spec delta for `extraction`, which this change no longer touches.

Kept, at the new place: `mime.by_name` and the exclusion in `detect_with_tie`.

**D7. The test formats of spec `recognition`'s scenarios** (review finding 9). `test/tags` handles files named `*.tags`, of type `application/x.test-tags` (a name rule only), which start with the 4 bytes `TAGS`; it reads those 4 bytes of each file of its type and says that a file without them is not of its type, with the reason "no TAGS header". `test/png` claims every file of type `image/png`, basis "PNG signature". `test/contradicts` says that every file of type `image/png` is not of that type, with the reason "not a picture". A variant of `test/tags` raises after its drops. They live in `tests/test_formats.py`, with the `.tags` rule in a MIME file of the test.

## The em part (decision 144; built here, since `dm-containers-and-k2is` is merged into `crawler`)

**E1. `em/dmw`, a format in `dm/` that claims `.dmw` files (decision 173).**
- Its settings: type `application/x.dm-dmw`, reacting to that type, priority 61. Its one name, "Gatan Digital Micrograph workspace" (@weber's "DM workspace"), is the type's comment in `dm.xml`, used by the description and, without a `display_name` of its own, by the subject (code review finding 7). Gatan's own name is still to be confirmed with his files (open items 155, 184).
- Recognition: for each file of type `application/x.dm-dmw` (by type, not by a name ending in `.dmw`: the glob matches `Up.DMW` too, review finding 5), it reads 16 bytes. With the DM4 header it claims the file as a dataset of one file, basis `Digital Micrograph header`. With the DM3 header too (decision 174), basis `Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet`. Without either it calls `d.not_of_type(e, "no DM header")`. The header tests are the DM3 and DM4 magic of `dm.xml`: `big32` 3 at offset 0 with `big32` 0 or 1 at offset 8, and `big32` 4 at offset 0 with `big32` 0 or 1 at offset 12; one function `dm.version(data) -> 3 | 4 | None` holds them for `em/dmw` and K2IS.
- Extraction: every tag of the file, `path value` phrases in the reader's order, values as the reader gives them, nothing left out (decision 173: "We just include everything"; the filter is a backlog TODO). `values` stays empty: nothing reads it yet. The tag walker is the one K2IS uses, moved to `dm/` with K2IS's user-interface filter as its argument; K2IS's output does not change.
- Why RosettaSciIO and not ncempy (173: "Can we use ncempy to extract allTags?"): we already read DM tag trees with RosettaSciIO's `DigitalMicrographReader` on our own handle (`dm.parsed`, with the small buffer and readahead off of F14), for DM images and for K2IS's `.gtg`. Its `tags_dict` is all the tags, which is what ncempy's `allTags` gives. One reader for the three formats keeps one set of quirks (the buffer, the pinned version) and adds no dependency; ncempy would be a second DM reader.
- What a real workspace holds (@weber's `exemplary_workspace.dmw`, saved by GMS on 2026-11-12 with two images open; read with `dm.parsed`): the DM4 header and root tags only, no `ImageList`: `File count 2`, `File name 0 .\exemplary_workspace\h1.dm4`, `File name 1 .\exemplary_workspace\100 deg C.dm4` (Windows paths relative to the workspace, to a folder of the images beside it), `Frame 0 None`, `Frame 1 None`, `Window 0 (217, 84, 646, 536)`, `Window 1 (641, -17, 835, 207)`, `Workspace name exemplary_workspace`; 846 bytes. One saved with "only unsaved data" has the same tags apart from its name. The description lists these as the reader gives them, backslashes included; the images it names are neither read nor grouped with it (decision 189: a for now; grouping is a backlog item). The file is the representative fixture `workspace`, unchanged, with @weber's agreement; the images are not in the repository.
- What becomes of a DM3 `.dmw` (decision 174): handled, and flagged in its basis as a file of interest, shown by `records --verbose` and `modama-chain trace` (decision 148's per-item tools). No new mechanism: it is the first concrete case of the backlog item "Suspicious results for manual follow-up".
- `extractor_version` "1", recognition `version` "1": the format is new.

**E2. K2IS checks a lone tag file (decision 172).**
- K2IS groups a `.gtg` with exactly 8 sector files of its stem whatever the `.gtg` holds, as today. An empty or broken `.gtg` of a capture fails at extraction and is reported: "broken".
- A `.gtg` with 1 to 7 or 9 and more sector files of its stem keeps its type and gets the warning about its number of sector files, as today: the sector files say it is a capture.
- Only a `.gtg` with no sector file of its stem (a lone `.gtg`) is checked: K2IS reads its first 16 bytes. With the DM4 header it keeps its type. With the DM3 header too, and K2IS calls `d.note(e, "file of interest: DM3 .gtg, review by hand")`, which puts the note into its basis without changing its type (decision 183: "accept, but flag as a 'file of interest' to be reviewed manually"; `Directory.note` is the core's way to note a file, put back like the drops when a call is discarded). Without either it calls `d.not_of_type(e, "no DM header")`.
- The longest-stem rule is unchanged, so a broken `scan_2_.gtg` with its 8 sector files next to a complete `scan_.gtg` is grouped as its own capture (review finding 3 resolved by 172).
- Its priority goes from 60 to 61 (D3's rule: a lone tag file without the DM4 header may be DM3, for `em/dm3`).
- Its recognition `version` goes from 1 to 2: its recognition changes. Its `extractor_version` stays 3.
- The warning for sector files without a tag file keeps its wording: a sector file without a `.gtg` of its stem is still exactly that.

**E4. `em/dmwx`, a compressed workspace (decision 190).**
- What GMS writes (@weber's `exemplary_workspace.dmwx`, 377 MB, observed 2026-11-12 from its first local header and its central directory only): a ZIP, no comment, whose first member is `exemplary_workspace/exemplary_workspace.dmw` (488 bytes, deflated; another, smaller workspace than the uncompressed one), then the directory entry `exemplary_workspace/files/` and the images `exemplary_workspace/files/h1.dm4` and `exemplary_workspace/files/100 deg C.dm4`, deflated.
- Type `application/x.dm-dmwx`, glob `*.dmwx`, a subclass of `application/zip` (the core's ZIP type, magic `PK\003\004`), comment "Gatan Digital Micrograph workspace (compressed)", the one name in description and subject. Priority 61, as `em/dmw`.
- Recognition reads the first 1,054 bytes (the 30-byte local header and a name of up to 1,024 bytes): a ZIP whose first member's name ends in `.dmw`, in any case, is claimed, basis `ZIP, first member a .dmw`. Anything else is not of the type ("no .dmw first in a ZIP"): a text file becomes `text/plain`, another ZIP `application/zip`. A read error keeps the type, as for `.dmw` (D1). The first member is what GMS writes first; checking the central directory would need a read at the end, which `Directory.read` does not offer.
- Extraction opens the file unbuffered, so that `zipfile` reads only what it asks for: the end record, the central directory and the inner `.dmw`. It parses that member with RosettaSciIO's reader on a `BytesIO` (`dm.parsed_from`, the reader `dm.parsed` uses on a file) and describes its tags as `em/dmw` does, then each member as `member <name> <uncompressed size> B`. No image is decompressed or read. Bytes read on the composed fixture: 737 of 7,830, the largest read 261 bytes.
- Fixture `compressed_workspace`, composed by a generator from two fixtures here, laid out as GMS writes it: the workspace of `workspace` and the DM4 image of `cl_image_dm4` (GPL-3.0-or-later) in `files/`. @weber's `.dmwx` holds his images and is not copied.

**E3. The documents of `dm-containers-and-k2is` and the XML comments.**
- The comments in `dm.xml` and `k2is.xml` that say "a name match that is a subclass of the sniffed type wins, so the DM4 format does not take it" become: the name decides the type, and the format checks the header (`em/dmw`, K2IS).
- `dm-containers-and-k2is`'s task 4.1 (its review finding 1) gets its outcome: this change, instead of the octet-stream globs.
- Its requirement "Tag files and workspaces are not DM images" and its K2IS requirement "A K2IS tag file and its sector files form one dataset" are modified by this change's deltas `formats/dm` and `formats/k2is`, archived after it.

## Flows of events

A crawl runs walk, then extraction, then store. In the walk, each file gets its type (`mime.detect_with_tie`): a single best name rule decides without reading, otherwise the content. Then the formats recognise each directory in priority order (`run_post`). With this change, a format may read a file's first bytes there and drop the type the name gave it. Extraction runs after the walk, in worker processes, on the datasets of formats with an extractor.

**Flow A, a stray `notes.gtg` holding `hello\n`.**
1. The walk types it `application/x.dm-gtg` by its name, without reading it.
2. `em/k2is` (priority 61) reacts to that type. `notes.gtg` has no sector file of its stem `notes`, so K2IS reads its first 16 bytes: there is no DM header. It calls `d.not_of_type(e, "no DM header")`.
3. The core finds the type came from the name alone. It detects again without `x.dm-gtg`: no other name rule, no content match, the bytes look like text, so `text/plain`. That read is not charged to `em/k2is`'s budget (decision 166); its own 16-byte read is.
4. No format claims the file. It becomes a single file of type `text/plain`, basis `single file; em/k2is: not application/x.dm-gtg, no DM header`.
5. No extraction runs, and there is no warning. The record says `dc:format text/plain`, "Plain text document, 1 file, 6 B, in …". `records --verbose` shows the basis in a comment, and `modama-chain trace` on its crawler line.
6. Next crawl, folder unchanged: the stored dataset is taken over, and nothing is read.
7. If the file is replaced by a real tag file, its size and times change, so the folder is recognised again. `em/k2is` finds the header, and the file stays `application/x.dm-gtg`, a lone `.gtg` as today.

An empty `empty.gtg` goes the same way and becomes `text/plain` (an empty file counts as text).

**Flow B, an empty `Capture7_.gtg` next to `Capture7_1.bin` to `Capture7_8.bin` (decision 172).**
1. The walk types `Capture7_.gtg` by its name and the sector files by their content.
2. `em/k2is` finds 8 sector files of the stem `Capture7_` and groups the 9 files as one K2IS dataset, without reading the `.gtg`.
3. Extraction reads the `.gtg` with the DM reader, which fails on the empty file ("unpack requires a buffer of 4 bytes"). The crawl reports `/Capture7_.gtg: em/k2is extraction failed: …`, and the record keeps a basic description: "K2IS acquisition, 9 files, …". This is "broken", as today.

A `.gtg` cut short after 1,000 bytes, or filled with zeros, goes the same way.

**Flow C, a broken `scan_2_.gtg` with `scan_2_1.bin` to `scan_2_8.bin`, next to a complete `scan_.gtg` with `scan_1.bin` to `scan_8.bin` (review finding 3).**
1. K2IS takes the longest stem first: `scan_2_` collects its 8 sector files, then `scan_` collects the 8 left.
2. Two K2IS datasets of 9 files each. Extraction succeeds for `scan_.gtg` and fails for `scan_2_.gtg`, which the crawl reports at `/scan_2_.gtg`. No warning blames `scan_`.

**Flow D, `.dmw` files (decisions 173, 174).**
1. The walk types `exemplary_workspace.dmw`, `old_workspace.dmw` and `notes.dmw` `application/x.dm-dmw` by their names.
2. `em/dmw` (priority 61) reads 16 bytes of each. `exemplary_workspace.dmw` starts with the DM4 header: a dataset of `em/dmw`, basis `Digital Micrograph header`. `old_workspace.dmw` starts with the DM3 header: a dataset of `em/dmw`, basis `Digital Micrograph header; file of interest: DM3, no .dmw in DM3 seen yet`. `notes.dmw` holds `hello\n`: `d.not_of_type(e, "no DM header")`, and it becomes a single file of type `text/plain`, basis `single file; em/dmw: not application/x.dm-dmw, no DM header`.
3. Extraction of the two `em/dmw` datasets: every tag, as "Gatan Digital Micrograph workspace" in `dc:subject` and the tags' `path value` phrases at the start of `dc:description` (for `exemplary_workspace.dmw` its 8 root tags, `File count 2, File name 0 .\exemplary_workspace\h1.dm4, …`), stored as every extraction is: each phrase cut to 4,096 characters (the DM3 stand-in's colour table, 6,053), at most 1,000 phrases.

A compressed workspace `exemplary_workspace.dmwx` goes the same way with `em/dmwx` (E4): its first member is a `.dmw`, so it is claimed, and its description gives that workspace's tags and the archive's members.

**Flow E, a DM3 image named `stem_image.dmw`.** It has the DM3 header, so `em/dmw` claims it as in flow D: a `.dmw` dataset with every tag of the image, marked as a file of interest, not a DM3 image. A harmless miss: nothing false is said about it (review finding 5).

**Flow F, a file typed by its content (145).** The DM4 magic (`dm/dm.xml`, priority 60) is `big32` 4 at offset 0 with `big32` 0 or 1 at offset 12. Take a file without a name rule, say `counts` (no extension, so no glob), written by NumPy as big-endian 32-bit integers `[4, 7, 9, 0]`. It starts `00000004 00000007 00000009 00000000` and matches, so it is typed `application/x.dm4`.
- `em/dm4` claims it without a check (its type comes from the content), and extraction fails in RosettaSciIO's parser ("unpack requires a buffer of 1 bytes"). This is reported as a failed DM4 extraction, which points an operator at the weak magic. Unchanged by this change.
- Had a format called `not_of_type` on it, the type would stay, with D2's warning.

The lean stays: no fallback for content-typed files. A collision on the content side is a bug in a magic rule, to be fixed with its example.

## Risks / Trade-offs

- [Format order decides whether the new type's format sees the file] → the order rule in TEMPLATE, priority 61 for the two em checkers, a test of each order, and the warning for a broken order (D3). If it bites, the alternative of D1 (a stage before recognition) removes the rule.
- [A checking format hides a broken file behind another type] → TEMPLATE: check the signature only (the header or magic a content rule would test), never parse to decide; and decide what is broken by the files around it before checking (K2IS checks only a lone `.gtg`). A truncated DM4 file still has its header, so it is claimed and fails at extraction as today.
- [Reads in the walk: `em/dmw` reads 16 bytes of every `.dmw`, 2,036 on staging (F15), and K2IS of every lone `.gtg`, 1 on staging] → one small unbuffered read each, only in directories that are recognised again.
- [Extraction of every `.dmw`: 2,036 more extractions on staging, each reading the tag tree] → the reader reads the tags only, in a 64 KiB buffer (F14), as for DM images; extraction runs in its worker pool with its time limit. The first crawl with this change extracts them once; later crawls reuse the result while the file is unchanged.
- [The uncharged re-detection reads up to 18,730 bytes per dropped file] → at most one per file typed by its name per recognition (D2); decision 166 accepts it until monitoring or a benchmark shows a drain.
- [A format that drops a type it does not react to] → allowed: there is no case for a guard yet. The note names the format.
- [Detection with a type left out loses a weaker content match: pyxdg's `match_data` returns the best magic match only] → cannot happen for `.gtg` and `.dmw`, whose types have no magic; stated in spec `mime-database` (review finding 10).

## Migration Plan

No schema change. The new format id `em/dmw`, K2IS's recognition `version` 2 and the changed bytes of `dm.xml` and `k2is.xml` change the rule-set fingerprint (`selection.py:138-165`; the distribution version of `modama-formats-em` stays `0.0.1.dev0`), so the first crawl recognises every directory again. That crawl extracts every `.dmw` (new datasets) and re-extracts nothing else: DM and K2IS extractions are reused while their extractor version and the files' stamps are the same. Whether staging has already been crawled with the merged DM/K2IS code is not recorded (review, "Not verified"); it does not change this plan. Rollback: the previous image. The stored datasets of the next crawl then carry the old types again.

## Open questions

- None open. **A lone DM3 `.gtg`** (review finding 5, its `.gtg` case; code review finding 2) was question 183, decided by @weber on 2026-11-12: "accept, but flag as a 'file of interest' to be reviewed manually" (E2). Before, by decision 147, such a file was dropped to `application/x.dm3`, claimed by `em/dm3` and described as a DM3 image. Test: `k2is/tests/test_with_the_dm_part.py`. No such file is known.
