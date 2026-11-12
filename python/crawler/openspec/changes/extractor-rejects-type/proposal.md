# Proposal

## Why

A file that only one name rule matches is typed by its name alone: detection returns before it reads the file (`mime.py:179-184`). With `dm-containers-and-k2is`, a text or empty `notes.gtg` or `x.dmw` is therefore described as "Gatan Digital Micrograph .gtg tag file" (review M1 of that change). That is a false statement to a searcher, the problem F15 set out to fix. The review proposed adding the globs to `application/octet-stream`, so that the content always decides. @weber (2026-11-12) prefers another mechanism: the extractor says "this is not, in fact, a Gatan gtg file". The file then falls back to another type. This works even for name collisions nobody knows about, and the name keeps its fast match. It applies to a stray file only. A dataset recognised as a group (a K2IS capture: `X_.gtg` plus 8 `.bin` sectors) whose anchor does not read is a broken dataset, a broken extractor or a variant we don't understand. It stays the group, and its extraction fails as today. Serves R25 (honest types), R30 (records that don't mislead a searcher), R23/R8 (a failure stays a reported failure), R10 (a re-crawl does no work for an unchanged file).

## What Changes

- An extractor can **reject** a dataset: "these files are not of my type", distinct from failing on them. The format author raises a dedicated exception with a reason (TEMPLATE).
- For a **single file typed by its name alone**, a rejection makes the dataset fall back. Its type becomes what detection gives without the rejected type: another name rule, else the content, else `text/plain` or `application/octet-stream`. Its record describes it as that type, and the crawl reports no warning. The fallback type's own extractor does not run.
- For **any other dataset** (several members, a directory, a collapsed tree, or a file typed by its content), a rejection is an extraction failure, reported as today. It is never re-recognised.
- A rejection is a **stored result**, tied to the extractor, its version and the dataset's stamp, like a failure on the file's content. The next crawl of unchanged data gives the same type without running the extractor.
- **In `modama-formats-em`**, this amends `dm-containers-and-k2is` and replaces the review's octet-stream globs. `.dmw` and `.gtg` keep their name rules. Two single-file formats check the DM4 header and reject files without it: one for `.dmw`, one for a `.gtg` that the K2IS grouping does not take. A lone `.gtg` therefore gets a format of its own, which it does not have today.

Behaviour towards the user: a searcher or harvester sees a stray `notes.gtg` holding text as `dc:format` `text/plain`, described as a plain text document. Today it is described as a Gatan tag file. An empty `x.dmw` becomes `text/plain`, as an empty file without a name rule is today. Their datestamps move once. A K2IS capture whose `.gtg` does not read stays one K2IS record, and the crawl reports its extraction failure as today. An admin sees no new warning or count. The `records` command's verbose note names the rejecting format (`notes.gtg: text/plain by em/gtg 1, …`). `.dmw` and lone `.gtg` files count as extractions run (2,036 and 1 on staging run 3, F15). Schema change: one new column, so the database is recreated.

Out of scope: running the fallback type's extractor, or recognising the directory again after a rejection. Rejecting files typed by their content. A count of rejections in the crawl report. Metadata from `.dmw` files. Generic extractors on subtypes (Q15).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `extraction`: an extractor may reject a dataset. A single file typed by its name alone then falls back to another type. Any other dataset keeps its type and its extraction fails. `extraction` is introduced by `em-formats-and-extraction`, which is archived first.

## Impact

- Crawler: `formats/__init__.py` (the exception, `Extraction.rejected`), `mime.py` (the type a name alone gives, and detection without a type), `extraction.py` (fallback or failure, reuse), `store.py` (column `extract_rejected`; recreate the database), `formats/TEMPLATE.md`, `README.md` (Extract), `BACKLOG.md`.
- `modama-formats-em` on branch `dm-containers`: formats `em/dmw` and `em/gtg`, reproducer fixtures (`notes.gtg` holding text, an empty `empty.dmw`), and that change's D1, its spec requirement "Tag files and workspaces are not DM images", the comments in `dm.xml`/`k2is.xml` and the outcome of review M1.
- No new dependency.

## Questions for @weber

- Where should the `em` part go: here, as task group 2 on branch `dm-containers`, or folded into `dm-containers-and-k2is` as its fix for M1, with this change keeping only the crawler part? Lean: fold it in, since it changes that change's D1 and spec. Against: then the two changes must land together.
- Should a file typed by its content also fall back when its extractor rejects it, for example a stray binary that happens to match DM4's three header fields? Lean: no, it fails as today (design D2). Against: such a collision is exactly the "collision we are unaware of" case, only on the content side.
- Should the fallback type's own extractor run? For example, a DM3 file named `.dmw` would then also get image metadata. Lean: not now (design D3). No such file has been seen.
- Should the `.dmw`/`.gtg` check accept the DM3 header too? Staging's `.dmw` and `.gtg` files all have the DM4 header (F15). Lean: DM4 only.
- Should an admin see rejections, as a count in the crawl report or as a note in `records -v`? Lean: no, until someone asks.
