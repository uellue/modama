# Design

## Context

See proposal.md, Why. The current state, with line numbers on `crawler` at e35e4b4:

- `mime.detect_with_tie` returns at once when one name rule is best (`mime.py:179-184`). The content is read only when no name rule matches or several tie (`mime.py:186-213`).
- A file that no format claims becomes a dataset with format `""` (`formats/__init__.py:366-380`). Only datasets of a format with an extractor are extracted (`extraction.py:100-102`). So a lone `.gtg` or a `.dmw` on `dm-containers` gets no extraction at all. The K2IS format claims a `.gtg` only with its 8 sectors (`k2is/__init__.py:209-229` on `dm-containers`), and nothing claims `.dmw`.
- `_fill` gives a format's dataset the format's type (`formats/__init__.py:268-273`). An extraction is reused when extractor id, version and stamp match and it is not `retry` (`extraction.py:114-121`). Datasets of unchanged directories are taken over with their stored type and extraction (`walk.py:302-303`). `dc:format` and the description's type come from `dataset.type` (`records.py:82,126`).

## Goals / Non-Goals

**Goals:** a stray file's record does not claim a type its content contradicts, while the name still decides at walk time; the same data gives the same type on every crawl.
**Non-Goals:** recognising a directory again during extraction; a fallback that runs another extractor; a check of files typed by their content.

## Decisions

**D1. A dedicated exception, `NotOfType(reason)`, in `modama_crawler.formats`.** `extract` raises it: "these files are not of my type", for example `raise NotOfType("no DM4 header")`. It runs in the worker process, and the pool hands it back to the parent like any exception (`extraction.py:270`). `_run` catches it before the generic `except` and reports a rejection outcome instead of an error. `Extraction` gains `rejected: str | None` (the reason), and `store.py` a column `extract_rejected`. TEMPLATE, "Extracting metadata": raise it only when the files lack the type's signature, the header or magic that a content check would have tested. Raise it before any parsing. A parse error after the signature matched stays a failure: a broken file is not another type.
*Alternative:* a result value (`Rejected(reason)` returned instead of `Extracted`). It is visible in the return type, but a check inside a helper would have to pass it up by hand. Failures are already exceptions, and a rejection is "this didn't work, for this reason".
*Strongest argument against:* an extractor that catches `Exception` around its reader also catches `NotOfType`. TEMPLATE says to raise it before the reader runs.

**D2. Which datasets fall back: a single file typed by its name alone.** The anchor is the dataset's only member, it has no parts, and the anchor's name alone gives the format's type. That means one best name rule, the early return at `mime.py:183`, factored out as `mime.by_name(name) -> str | None`. This is recomputed from the name and the active MIME database at extraction time: a pure function, with no new field on `Entry` or `Dataset`. Every other rejection becomes an error `repr(NotOfType(...))`, stored and reused as a failure on the file's content (not `retry`), and reported by the existing warning (`extraction.py:147-152`). That covers a K2IS capture (9 members), a directory or collapsed dataset (the anchor is not a member) and a file typed by its content. This is @weber's distinction: a stray file versus a group, which is "a broken dataset, a broken extractor or a variant we don't understand".
*Alternative:* any single-file dataset, also one typed by its content. That would cover a weak magic collision, a stray binary matching DM4's three header fields. *Against it:* a content match is positive evidence, and the extractor cannot tell "not mine" from "broken" beyond what the magic already checked. Left as a question.
*Where the rule does not decide by itself:* a single file of a subdirectory that a collection format adopted as a part. Its own dataset qualifies, so its type falls back, and the parent's claim stands, as in scenario 2.

**D3. The fallback type: detection again without the rejected type.** `mime.detect_with_tie(path, exclude={type})` follows the checking order unchanged and drops the excluded type from the name candidates and from the sniffed result. So: another name rule if one remains, else the content, else `text/plain` or `application/octet-stream` (spec `mime-database`). A tie among the rest resolves to the common ancestor as usual and is not reported. For `notes.gtg` holding text, this gives `text/plain`. An empty `empty.dmw` gets `text/plain`, as an empty file without a name rule does today (checked on the `dm-containers` MIME database: `empty` → `text/plain`). A DM3 file named `.dmw` would get `application/x.dm3` from its magic (not run). The fallback type's own extractor does not run: extraction does not recognise. There is one step, so a rejection cannot chain. The record names the right type even where it lacks that type's metadata.
*Alternatives:* the next name candidate only (nothing left for `.gtg`, so it says nothing). The parent in the sub-class hierarchy (`application/x.dm4` for a text file: false, the same error one level up). Always `application/octet-stream` (true, but less informative than `text/plain`).
*Strongest argument against:* the DM3 `.dmw` above, and generally a misnamed file of a type that has an extractor, loses its metadata. No such file has been seen ("Not now").

**D4. Where: in `extraction.extract`, in the parent, after the pool.** The datasets that were run and those reused are handled alike. For a qualifying rejection, the type becomes the fallback. When the dataset already carries a type other than the format's (taken over from the store), that type is kept without reading the file. Otherwise the type is detected again: one read of at most the magic length, only for rejected files of re-recognised directories. A changed MIME database therefore shows: it changes the fingerprint, so those directories are recognised again. In every other case the type is the format's type, so a file that stops being rejected gets it back. The dataset keeps its format, anchor, members, basis and stamp. Keeping the format is what lets the next crawl reuse the rejection and lets a new extractor version run again. The crawl report counts it as run or reused, never as failed.
*Alternative:* turn the dataset into the core's single file (format `""`). The `records` note would then be a plain count. But a taken-over dataset would leave extraction (`extraction.py:144-146`), and a new extractor version would never reach it.

**D5. The `em` part: amends `dm-containers-and-k2is` D1 and resolves its review M1.** `.dmw` and `.gtg` keep their globs. Two single-file formats in `modama-formats-em`:
- `em/dmw` in `dm/` (type `application/x.dm-dmw`).
- `em/gtg` in `k2is/` (type `application/x.dm-gtg`, priority below K2IS). It yields only the `.gtg` files the K2IS grouping leaves; the grouping is one function both formats call, so no "already claimed" warnings.

Their extractor reads the 16-byte header and raises `NotOfType` without the DM4 header. Otherwise it returns `None`, since metadata from `.dmw` files is out of scope there. The K2IS extractor is unchanged: its anchor failing is scenario 2. The `dm-containers` spec requirement "Tag files and workspaces are not DM images" becomes: "A file named `*.dmw` or `*.gtg` SHALL be typed by its name … ; one without the DM4 header falls back (spec `extraction`)". D1's sentence "the name match, being its subclass, wins" and the matching comments in `dm.xml` and `k2is.xml` are corrected: that rule acts only on tied names (review M1).
*Alternative:* the review's octet-stream globs. They are simpler, with no new formats, but every `.gtg`/`.dmw` is then sniffed in the walk, and they help only with collisions we know about.

## Flows of events (for @weber's 145 and 146)

A crawl runs walk, then extraction, then store. In the walk, each file gets its MIME type (`mime.detect_with_tie`: a single best name rule decides without reading; otherwise the content), then the formats recognise datasets per directory (`run_post`). Extraction runs after the walk, in worker processes. Each flow below is told twice: as designed here (rejection at extraction), and with the alternative of question 149 (the format checks the header while it recognises, and can drop the name's type then).

**Flow A, a stray `notes.gtg` holding text.**
- Here: (1) the walk types it `application/x.dm-gtg` by its name, without reading. (2) K2IS finds no sectors; `em/gtg` claims it as a single-file dataset. (3) Extraction: `em/gtg` reads 16 bytes, no DM4 header, raises `NotOfType("no DM4 header")`. (4) In the parent: one member, typed by name, so it qualifies; detection again without `x.dm-gtg` reads the content: `text/plain`. The dataset keeps format `em/gtg`, the type becomes `text/plain`, the rejection is stored with extractor, version and stamp. (5) Store: the record says `dc:format text/plain`, no warning. (6) Next crawl, folder unchanged: taken over with its stored type, no read. (7) The file replaced by a real tag file: its stamp changes, the folder is recognised again, the extractor accepts: `x.dm-gtg`.
- With 149: (1) as here. (2) `em/gtg`'s recognition reads 16 bytes (`Directory.read`), no DM4 header, drops the name's type: detection without it gives `text/plain`; `em/gtg` does not claim the file; it becomes an ordinary single-file dataset `text/plain`. Steps 3 and 4 do not happen; nothing extra is stored; steps 5 to 7 as here.

**Flow B, a text `X_.gtg` next to 8 valid sector files.**
- Here: recognition groups them by name and sector magic into one K2IS dataset of 9 files; extraction fails on the tag file; 9 members, so no fallback: an extraction failure with a warning, "a broken K2IS capture".
- With 149: K2IS's recognition reads the tag file's header first, no DM4 header, so no capture: `X_.gtg` falls back to `text/plain`, the 8 sectors stay single files with the warning for sectors without a tag file. "Not K2IS", decided before grouping; a capture whose tag file has the header but fails later stays "broken".

**Flow C, the fallback type's own extractor (146): a DM3 file named `conditions.dmw`.**
- Here: typed `x.dm-dmw` by name; `em/dmw`'s extractor finds no DM4 header and rejects; detection again by content gives `application/x.dm3` (its magic); the extractor of DM3 does not run (D3, one step, no chains): the record says "DM3 image" without its metadata. Letting it run would mean a second extraction round in the parent, after the pool.
- With 149: `em/dmw`'s recognition rejects the name's type; detection gives `x.dm3`; the DM3 format then claims it in the same recognition pass, if it comes after `em/dmw` in the formats' order, and its extractor runs as for any DM3 file: image metadata with no extra mechanism. If DM3 `.dmw` files turn out to be workspaces too (147), the check accepts the DM3 header as well.

**Flow D, a file typed by its content (145).** The DM4 magic (`dm/dm.xml`, priority 60) is `big32` 4 at offset 0 with `big32` 0 or 1 at offset 12. A file without a name rule, say `counts` (no extension, so no glob), written by NumPy as big-endian 32-bit integers `[4, 7, 9, 0]`, starts `00000004 00000007 00000009 00000000` and matches: typed `application/x.dm4`, claimed by `em/dm4`, extraction fails in RosettaSciIO's parser. As designed here (D2: content-typed files do not qualify) that is reported as a failed DM4 extraction, which an operator can see and which points at the weak magic. With a fallback for content-typed files, it would quietly become `application/octet-stream`. The lean stays: no fallback for content-typed files; a collision on the content side is a bug in a magic rule, to be fixed with its example.

## Risks / Trade-offs

- [A rejecting extractor hides a broken file behind another type] → TEMPLATE limits rejection to a missing signature, checked before parsing. A truncated DM4 file still has its header and fails as today.
- [The `records` note says `notes.gtg: text/plain by em/gtg 1`, which reads as if em/gtg chose text] → acceptable for an admin's verbose output. Naming the rejection there needs a request ("Not now").
- [2,036 `.dmw` files become extraction tasks] → a 16-byte read each, once, then reused. That is cheap next to the failures they replace (F15).
- [Schema change] → recreate the database, as after every schema change (`store.py:63`). Landing with `dm-containers` makes it one re-crawl, not two.

## Migration Plan

Recreate the database on staging when this lands. The first crawl re-extracts DM files anyway (`dm-containers`, extractor version 3). Rollback: the previous image and a recreated database.
