# Design

## Context

See proposal.md, Why. The current state, with line numbers on `crawler` at 99b6f58 (the em lines on `dm-containers` at 8c72002):

- `mime.detect_with_tie` returns at once when one name rule is best (`mime.py:177-184`). The content is read only when no name rule matches or several tie (`mime.py:186-213`). It reads `Mime.magic.maxlen` bytes, 18,730 with the core's definitions (measured with pyxdg on the core database).
- A format reads through `Directory.read(entry, n)`, within a byte budget of 1 MiB per format call (`formats/__init__.py:175-184`, `BYTE_BUDGET` at 235). The read is refused for an entry object that is not the directory's current one (`formats/__init__.py:177-178`).
- `run_post` runs the formats in `ordered` order: priority descending, then format id (`formats/__init__.py:238-239`). It computes the types present, which decide whether a format reacting to types is called, once before the loop (`formats/__init__.py:304`). It takes the types of unclaimed files from the same snapshot (`formats/__init__.py:305, 366-380`). `_call` turns an exception or an over-budget read into a warning and discards that format's datasets for the directory (`formats/__init__.py:242-259`).
- `_fill` gives a format's dataset the format's type (`formats/__init__.py:262-274`). An unclaimed file becomes a single-file dataset of its detected type with basis `single file` (`formats/__init__.py:366-380`).
- Type and basis are stored per dataset (`store.py:72-79`, written at 299, read back at 372). An unchanged directory is taken over with its stored datasets, and no file of it is read (`walk.py:265, 302-303`). "Unchanged" means the same listing digest: names, kinds, sizes, owners and times of the entries (`walk.py:91-97`), under the same rule set. The rule set's fingerprint covers the enabled format ids and recognition versions, the distribution versions and the MIME definitions (`selection.py:138-165`).
- `dc:format` and the description's type come from `dataset.type` (`records.py:82`).
- On `dm-containers`, `.dmw` and `.gtg` have globs of their own types, `application/x.dm-dmw` (`dm/dm.xml`) and `application/x.dm-gtg` (`k2is/k2is.xml`). The DM3 and DM4 formats `em/dm3` and `em/dm4` have priority 60 (`dm/__init__.py:72`), and so has K2IS `em/k2is` (`k2is/__init__.py:38`). K2IS reacts to the `.gtg` and sector types and groups a `.gtg` with 8 sector files of its stem (`k2is/__init__.py:43-78`). Nothing claims a `.dmw` or a lone `.gtg`.

## Goals / Non-Goals

**Goals:**
- A file's record does not claim a type its content contradicts, where the format of that type can tell. The name still decides at no cost for every other format.
- "Not of this type" is decided before grouping, so that it is kept apart from "of this type, but broken".
- The same data gives the same result on every crawl, with nothing new stored.

**Non-Goals:**
- A check of files typed by their content.
- Calling a format again after a later format changed a type.
- Rejection at extraction.

## Decisions

**D1. `Directory.not_of_type(entry, reason) -> Entry`, during the post-order call.** A format calls it while recognising, after reading the file's first bytes through `d.read`, for example `d.not_of_type(e, "no DM4 header")`. The core then does the following:
- It checks that the type came from the name alone, by D2. Otherwise the type stays and the call is answered by D2's warning.
- It detects the type again without the dropped one: `mime.detect_with_tie(entry.path, exclude=frozenset({entry.mime}))`. This follows the checking order unchanged and leaves the excluded type out of the name candidates (the best weight and length are taken among the rest). A sniffed result equal to it counts as no match. So the result is another name rule if one remains, else the content, else `text/plain` or `application/octet-stream` (spec `mime-database`, "Fallback types"). A tie among the rest is reported as the walk reports one. Matching runs in the calling thread: the walk's matching processes are not passed to formats, and drops are rare.
- It charges `min(entry.size, Mime.magic.maxlen)` bytes for that read to the format call's budget, before reading. Every byte a format call causes to be read counts (spec `recognition`, "Budgets bound every format call"). For a 6-byte `notes.gtg` that is 6 bytes. A read error propagates to the format, and `_call` handles it as any read error: a warning, and the directory is recognised again next crawl.
- It replaces the entry in the directory's entries and name index with `replace(entry, mime=new)` and returns the new entry. The old entry object is refused by `d.read` from then on, as an entry of another directory is.
- It keeps a note for the file: format id, dropped type, reason. D4 says where the note goes.

The call is refused with `ValueError` in the pre-order call, where entries have no type, and for an entry of another directory, as `d.read` refuses one.

*Alternative:* a separate stage before recognition, a second method such as `Format.not_of_type(d) -> Iterable[(entry, reason)]` that the core calls on every format before any `recognize`. This is closer to @weber's first framing, "a stage where the extractor is asked 'do you accept this file'". It needs no order rule (D3), since every drop happens before any format recognises. *Against it:* a second method for every format author, and a second call per format and directory. K2IS would read each tag file's header in one method and group in the other. D1 is what question 149 put to @weber and what he accepted. The alternative is the fallback if the order rule turns out to be a trap.
*Strongest argument against D1:* the result depends on format order (D3).

**D2. Which files: typed by their name alone.** The core recomputes whether the entry's type is the one best name rule's: `mime.by_name(name) -> str | None`, factored out of `detect_with_tie` (`mime.py:177-184`) with no change of result. It is a pure function of the name and the active MIME database, so there is no new field on `Entry`.

If `by_name(entry.name) != entry.mime`, the type stays. That covers a file typed by its content, by a tie the content decided, or by an earlier drop. The directory then gets the warning "`<format>: <file> is not <type> (<reason>), but that type does not come from its name alone; type kept`". This follows decision 145: a content match is positive evidence. When a format contradicts it, the content rule is too weak and is to be fixed with its example (flow D). So it is reported, not hidden.

A file's type is therefore dropped at most once per crawl, and the fallback type is not checked again: one step, no chains.

Grouped datasets need no rule of their own. A format that groups files checks its anchor before it groups (K2IS, flow B), so "not of this type" is decided before a group exists. A group whose files passed the check and whose extraction fails stays an extraction failure, as today.

**D3. When the new type takes effect: at once, for the formats that run after.** `run_post` recomputes the types present from the directory's current entries before each format. It builds the single-file datasets from the current entries after the last format. A format that ran before the drop is not called again.

So the order rule: **a format that drops types SHALL have a higher priority than every format of a type its files may fall back to.** Equal priorities sort by format id, and `em/dm3` < `em/dm4` < `em/dmw` < `em/k2is`. At 60, a DM3 file named `conditions.dmw` would fall back to `application/x.dm3` after `em/dm3` had run, and stay an unclaimed single file without metadata. Hence priority 61 for `em/dmw` and `em/k2is` (section "To fold into dm-containers-and-k2is"). TEMPLATE states the rule. A test for each order (spec `recognition`, the two scenarios of a later and an earlier format) documents it.

A format call that fails or exceeds its budget leaves every type as it was. `_call` keeps the entries as they were before the call and puts them back when it discards the call's datasets. Otherwise a format's half-finished work would change other formats' input while its own result is thrown away.

**D4. What the record and the diagnostics show.** The record shows the new type: `dc:format` and the description's type name come from it. The note goes into the basis of the dataset whose members include the file, appended as `"; <format>: not <type>, <reason>"`:
- a single file: `single file; em/k2is: not application/x.dm-gtg, no DM4 header`;
- a dataset a later format made of it: `Digital Micrograph header; em/dmw: not application/x.dm-dmw, no DM4 header`.

`records --verbose` already comments every dataset a format produced with its type and basis (`cli.py:548-551`). A single file now gets a comment too when its basis is not plain `single file`. It is still counted among the single files in the closing comment. `modama-chain trace` shows the basis of the dataset holding the item on its crawler line, for every dataset: one rule, and the basis is the crawler's per-item "why". There is no warning, and the crawl report has no count (decision 148).
*Alternative:* a field of its own on `Dataset` and a column. Clearer to query, but a schema change for a note that the two per-item tools can show from the basis.

**D5. What is stored, and the next crawl: nothing new.** The type and the basis go into `datasets` as for any dataset (`store.py:72-79`). There is no `extract_rejected` column, no schema change and no database recreation.
- A crawl of an unchanged directory under the same rules takes over the stored datasets with their type and basis. No file is read and no format is called (`walk.py:302-303`).
- A changed file changes the listing digest, so the directory is recognised again and the format checks again. If the file now has the header, it gets its name type back.
- A new or changed checking format changes the rule-set fingerprint by its id and version, or its distribution's version. Every directory is then recognised again once.

So the result is a function of the listing, the files' first bytes and the rules, as recognition is today: the same data gives the same result.

**D6. What the first version needed only for rejection at extraction is removed:**
- The exception `NotOfType` and `Extraction.rejected`.
- The column `extract_rejected`, with the schema change and the database recreation.
- The second detection in the parent after the extraction pool, and the rule for keeping a taken-over type there.
- The format `em/gtg`, and the grouping function that K2IS and `em/gtg` would have shared.
- The extraction tasks for 2,036 `.dmw` files and 1 lone `.gtg` on staging: no extractor of these types runs now.
- The spec delta for `extraction`, which this change no longer touches.

Kept, at the new place: `mime.by_name` and the exclusion in `detect_with_tie`.

## Flows of events

A crawl runs walk, then extraction, then store. In the walk, each file gets its type (`mime.detect_with_tie`): a single best name rule decides without reading, otherwise the content. Then the formats recognise each directory in priority order (`run_post`). With this change, a format may read a file's first bytes there and drop the type the name gave it. Extraction runs after the walk, in worker processes, on the datasets of formats with an extractor. The em formats are those of the section below.

**Flow A, a stray `notes.gtg` holding `hello\n`.**
1. The walk types it `application/x.dm-gtg` by its name, without reading it.
2. `em/k2is` (priority 61) reacts to that type. Before grouping, it reads the file's first 16 bytes: there is no DM4 header. It calls `d.not_of_type(e, "no DM4 header")`.
3. The core finds the type came from the name alone. It detects again without `x.dm-gtg`: no other name rule, no content match, the bytes look like text, so `text/plain`. 6 bytes are charged to `em/k2is`'s budget.
4. No format claims the file. It becomes a single file of type `text/plain`, basis `single file; em/k2is: not application/x.dm-gtg, no DM4 header`.
5. No extraction runs, and there is no warning. The record says `dc:format text/plain`, "Plain text document, 1 file, 6 B, in …". `records --verbose` shows the basis in a comment, and `modama-chain trace` on its crawler line.
6. Next crawl, folder unchanged: the stored dataset is taken over, and nothing is read.
7. If the file is replaced by a real tag file, its size and times change, so the folder is recognised again. `em/k2is` finds the header, and the file stays `application/x.dm-gtg`, a lone `.gtg` as on `dm-containers` today.

**Flow B, a text `X_.gtg` next to `X_1.bin` to `X_8.bin`, each starting with a K2IS block header.**
1. The walk types `X_.gtg` by its name and the sector files by their content.
2. `em/k2is` reads `X_.gtg`'s header before grouping: there is none, so it drops the type, and the file becomes `text/plain`. No tag file is left, so there is no capture.
3. The 8 sector files are unclaimed. K2IS reports them with its warning for sector files without a tag file of their stem. They stay single files of the sector type.

This is "not K2IS". Compare a capture whose `Capture52_.gtg` has the header but is cut short after 1,000 bytes. It passes the check and is grouped into one K2IS dataset of 9 files. Its extraction then fails in the DM reader and is reported as an extraction failure: "broken", as today.

**Flow C, a DM3 image named `conditions.dmw`.**
1. The walk types it `application/x.dm-dmw` by its name.
2. `em/dmw` (priority 61) reads its first 16 bytes: version 3, no DM4 header. It drops the type.
3. Detection without `x.dm-dmw` finds no other name rule and matches the DM3 magic: `application/x.dm3`.
4. `em/dm3` (priority 60) runs later and is called, because the type is now present. It claims the file: one DM3 dataset, basis `Digital Micrograph header; em/dmw: not application/x.dm-dmw, no DM4 header`.
5. The DM3 extractor runs as for any DM3 file: image metadata.

If the file were a DM3 workspace with no image, the DM3 extraction would fail and be reported. Decision 147 revisits that with @weber's fresh `.dmw` files.

**Flow D, a file typed by its content (145).** The DM4 magic (`dm/dm.xml`, priority 60) is `big32` 4 at offset 0 with `big32` 0 or 1 at offset 12. Take a file without a name rule, say `counts` (no extension, so no glob), written by NumPy as big-endian 32-bit integers `[4, 7, 9, 0]`. It starts `00000004 00000007 00000009 00000000` and matches, so it is typed `application/x.dm4`.
- `em/dm4` claims it without a check (its type comes from the content), and extraction fails in RosettaSciIO's parser. This is reported as a failed DM4 extraction, which points an operator at the weak magic.
- Had a format called `not_of_type` on it, the type would stay, with D2's warning.

The lean stays: no fallback for content-typed files. A collision on the content side is a bug in a magic rule, to be fixed with its example.

## Risks / Trade-offs

- [Format order decides whether the fallback type's format sees the file] → the order rule in TEMPLATE, priority 61 for the two em checkers, and a test of each order. If it bites, the alternative of D1 (a stage before recognition) removes the rule.
- [A checking format hides a broken file behind another type] → TEMPLATE: check the signature only (the header or magic a content rule would test), never parse to decide. A truncated DM4 file still has its header, so it is grouped or claimed and fails at extraction as today (flow B, the cut `Capture52_.gtg`).
- [Reads in the walk: `em/dmw` reads 16 bytes of every `.dmw`, 2,036 on staging (F15), and K2IS of every `.gtg`, 33] → one small unbuffered read each, only in directories that are recognised again. This replaces a read at extraction in the first version. The review's octet-stream globs would have read `Mime.magic.maxlen` bytes of each.
- [A directory with many dropped files exhausts the budget: each re-detection charges up to 18,730 bytes, so about 56 drops of large files per directory] → the format is skipped there with the budget warning, and every type is put back (D3). No such directory is known. A text file costs only its size.
- [A format that drops a type it does not react to] → allowed: there is no case for a guard yet. The note names the format.

## Migration Plan

No schema change. When this and `dm-containers` land together, the new formats and K2IS's version change the rule-set fingerprint, so the first crawl recognises every directory again. That crawl re-extracts DM files anyway (`dm-containers`, a new extractor version). Rollback: the previous image. The stored datasets of the next crawl then carry the old types again.

## To fold into dm-containers-and-k2is

This is the em part, decision 144. It moves into the change `dm-containers-and-k2is` on branch `dm-containers` once that branch is free, and is then removed here. It amends that change's D1 and its spec deltas `formats/dm` and `formats/k2is`, and resolves its review finding 1 (`.dmw` and `.gtg` typed by their name, whatever the content).

**E1. `em/dmw`, a checking format in `dm/`.**
- Its settings: type `application/x.dm-dmw`, reacting to that type, priority 61, no extractor.
- For each `.dmw` file it reads 16 bytes. Without the DM4 header it calls `d.not_of_type(e, "no DM4 header")`. The header test is the DM4 magic of `dm.xml`: `big32` 4 at offset 0, and `big32` 0 or 1 at offset 12.
- It yields no datasets. A `.dmw` with the header stays a single file of `application/x.dm-dmw`, as on `dm-containers` today.
- It accepts DM4 only, until @weber's fresh `.dmw` files (decision 147).

**E2. K2IS checks its tag files before grouping.**
- Before grouping, `em/k2is` reads 16 bytes of every `.gtg` of the directory, lone ones too, and drops the type of those without the DM4 header. It groups the rest as today.
- Its priority goes from 60 to 61 (D3's rule: a tag file without the DM4 header may be DM3).
- Its recognition `version` goes up, so that a staging database crawled with `dm-containers` recognises again. Skip this if `dm-containers` has not been crawled with by then.
- The warning for sector files without a tag file names what is missing: "… without a .gtg tag file of their stem with the DM4 header, for example X_1.bin". With a text `X_.gtg` right next to them, the old wording "without a .gtg file" would be false (review finding 3's point).

**E3. Amendments to the change's documents.**
- D1's sentence "the name match, being its subclass, wins", and the comments in `dm.xml` and `k2is.xml` that say the same, become: the name decides, and the format checks the header.
- The requirement "Tag files and workspaces are not DM images" is reworded as below.
- The review's finding 1 gets its outcome: this design, instead of the octet-stream globs.

**Spec text for `formats/dm` (replaces the requirement "Tag files and workspaces are not DM images"):**

> ### Requirement: Tag files and workspaces are not DM images
> A file named `*.dmw` or `*.gtg` that starts with the DM4 header SHALL be typed by its name with a type of its own, a subclass of the DM4 type, and SHALL NOT be described or extracted as a DM image. One that does not start with the DM4 header SHALL get the type detection gives without its name's type (spec `recognition`).
>
> #### Scenario: A .dmw file with the DM4 header
> - **WHEN** a file named `conditions_00C.dmw` starts with the DM4 header and holds no image
> - **THEN** its type is the `.dmw` type, its record does not name it a Digital Micrograph image, and no extraction fails for it
>
> #### Scenario: A lone .gtg file
> - **WHEN** a file named `IDES_DMS_Config.gtg` starts with the DM4 header and no sector files share its stem
> - **THEN** its type is the `.gtg` type and it is a dataset of one file
>
> #### Scenario: A text file named like a workspace
> - **WHEN** a directory holds `notes.dmw` holding `hello\n`
> - **THEN** its record has `dc:format` `text/plain` and describes it as a plain text document, and the crawl reports no warning for it
>
> #### Scenario: An empty file named like a workspace
> - **WHEN** a directory holds an empty `empty.dmw`
> - **THEN** its record has `dc:format` `text/plain`, the type an empty file without a name rule gets, and the crawl reports no warning for it
>
> #### Scenario: A DM3 image named like a workspace
> - **WHEN** a directory holds `stem_image.dmw`, a copy of the DM3 fixture `stem_image_dm3`
> - **THEN** it is one DM3 dataset whose record carries the same extracted values as the fixture's, and the dataset's basis names `em/dmw` and "no DM4 header"

**Spec text for `formats/k2is`:**

> ### Requirement: A K2IS capture needs a tag file with the DM4 header
> The K2IS format SHALL group only a `.gtg` file that starts with the DM4 header. A `.gtg` file without it SHALL get the type detection gives without the `.gtg` type (spec `recognition`), and sector files of its stem SHALL be reported as sector files without a tag file.
>
> #### Scenario: A text file named like a tag file
> - **WHEN** a directory holds `notes.gtg` holding `hello\n` and no sector files
> - **THEN** its record has `dc:format` `text/plain` and describes it as a plain text document, and the crawl reports no warning for it
>
> #### Scenario: A capture whose tag file is text
> - **WHEN** a directory holds `X_.gtg` holding `hello\n` and `X_1.bin` to `X_8.bin`, each starting with a K2IS block header
> - **THEN** there is no K2IS dataset; `X_.gtg` is a single file of type `text/plain`; the 8 sector files are single files of the sector type; and the crawl reports one warning for the directory, naming sector files without a tag file of their stem
>
> #### Scenario: A capture whose tag file is cut short
> - **WHEN** a directory holds `Capture52_.gtg` cut after its first 1,000 bytes, so that it keeps its DM4 header, and its 8 sector files
> - **THEN** the result has one K2IS dataset with 9 members anchored at `Capture52_.gtg`, and the crawl's warnings name `Capture52_.gtg` and the K2IS extraction failure

The existing scenarios "A capture with its 8 sectors" and "A tag file without sectors" stay as they are. Their `.gtg` files have the DM4 header.
