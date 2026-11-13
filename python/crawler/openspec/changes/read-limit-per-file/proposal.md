# Proposal

## Why

A format call's reads during recognition are bounded by a byte budget of 1 MiB per folder (`formats.BYTE_BUDGET`). Past it, `Directory.read` raises `BudgetExceeded` and the core drops the format's whole result for that folder, warning `<format> skipped: …`. `em/mrc` reads 211 bytes of each MRC file, so a folder of more than about 4,970 MRC files loses the MRC format entirely, while the same files spread over subfolders keep it. The number depends on the folder's size, not on what the format does with a file ("the limit per folder is arbitrary", @weber).

Request: @weber, 329 (2026-11-13): "yes, build the per-file limit. I'm not sure if we got it right everywhere, but it puts a limit to a file or format going completely overboard. Maybe flag more than 64 kB, stop at 1 MB, with the exception of allowlisted formats like HDF5?" On the open point whether the stop drops the file or the format's result for the folder: "Drop only the file -- why drop the folder??"

## Assumptions and leans

- **I read "1 MB" and "64 kB" as 1 MiB and 64 KiB**, the units the code uses (`1 << 20`).
- **Counted per file and format call**: the bytes a format reads of one file through `d.read` in one call, all reads of that file added. The core's read for a file's new type after a drop stays uncounted (decision 166).
- **Flag**: more than 64 KiB of one file (64 KiB exactly is not flagged: `em/empad` reads 64 KiB of its header). One warning per file and call, with the fixed marker `read more than 64 KiB`, for `modama-chain review`; the reads go on.
- **Stop**: a read that would take the count past the limit is refused before it reads, as `files.Counted` refuses for `inspect`, and so is every later read of that file in the call. The refusal drops only that file from the format's claims: the format skips it as a file it cannot read, the file stays as it would be without that format, and a warning with the marker `over its read limit` names the format and the file. Not tried again: the same file gives the same outcome. Against: a format that does not catch the refusal (a bug) still loses its result for the folder.
- **Allowlist**: a format declares a larger limit as a class attribute, `read_limit`, an explicit number reviewed with its code. `common/hdf5links` declares its 4 MiB, until now `links.BUDGET` passed to `inspect`; `inspect` takes the calling format's limit, so one number bounds both readers. Its behaviour stays as it is; only its warning's wording changes to the shared marker.
- **The review list**: `modama-chain review` gets the two markers as kinds of their own.

## What Changes

- The core: the per-folder budget goes; `Directory.read` counts per file, flags past 64 KiB and refuses past the format's `read_limit` (default 1 MiB) with `BudgetExceeded`, now an `OSError`; `cannot_read` and `did_not_answer` treat that refusal as warned and final; `inspect` uses the format's limit; `run_pre`/`run_post` lose their `byte_budget` parameter.
- Formats: `em/mrc` and the skeleton catch a read error per file (they did not: one file's error ended the call); `common/hdf5links` declares `read_limit`.
- `modama-chain review`: the kinds `read more than 64 KiB` and `over its read limit`.
- Docs: the spec `recognition`, TEMPLATE.md (the readers, the checklist), the README, the decision log, BACKLOG.

Behaviour towards the user: a folder of many files of one format is recognised as the same files in subfolders are (10,000 MRC files: 10,000 `em/mrc` datasets instead of 10,000 single files); a format that reads more than 64 KiB of a file leaves a warning, which `review` lists; a file a format may not read further keeps its single-file dataset and a warning, where the folder's whole result for that format went before. Folders whose format was skipped under the old rule stay so until their listing changes (the fingerprint has no version of the core's code): `crawl --path`, or a raised crawler version.

Out of scope: flagging reads through `inspect`; a time bound per file; the per-format read sizes beyond listing them (design).

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `recognition`: the byte budget per format call becomes a read limit per file, with a flag and a declared larger limit.

## Impact

- `python/crawler/src/modama_crawler/formats/__init__.py`, `files.py`, `walk.py`, `formats/skeleton/`, TEMPLATE.md, README, BACKLOG, `design/architecture.md`.
- `python/modama-formats-em/src/modama_formats_em/mrc/`, `python/modama-formats-common/src/modama_formats_common/pydata/`.
- `python/search-chain/src/modama_chain/review.py`, its README.
- No new dependency, no migration. The extractor identity changes with the installation, as with every code change.
