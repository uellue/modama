# Design

## D1. What is counted

Per format call, per file: the bytes `d.read` returned for that file, all its reads added. A read is refused when the count plus the bytes it asks for would pass the limit, before anything is read; that is the rule `files.Counted` already applies to `inspect` (count what was read, check what is asked). The flag is on what was read: a format asking for 64 KiB of a 1 KiB file is not flagged. Once refused, a file stays refused for the rest of the call, as `Counted` stays raised after a breach (review of hdf5-links, S12): the outcome does not depend on what the format tries after the refusal.

The count starts afresh at each format call (the pre-order and the post-order call are two calls). The core's own read for a file's new type after `not_of_type` is not counted (decision 166).

## D2. The refused file, not the format's result for the folder

@weber (329): "Drop only the file -- why drop the folder??"

Why the old rule discarded the whole call: the budget was the folder's, so passing it said nothing about one file; and `recognize` is a generator, which an exception ends half way. A partial result could hold multi-file groups made from what the format had read so far, with the rest of the folder's files never looked at, so the core threw away everything the call made, its type drops and warnings included (recognition-checks-content D3).

Why that no longer holds: the limit is per file, so a refusal is about one file, and it is raised as an `OSError` (`BudgetExceeded` now subclasses it). Every format already catches an `OSError` around its own `d.read` of one file and calls `d.cannot_read`, skipping that file and going on, so that one unreadable file does not decide the others' outcome (spec recognition, "A read error on one file"). A refused file then simply isn't a member of any of that format's datasets, as a file claimed by an earlier format isn't (344): the format builds its groups from the files it could read. The file stays as it would be without the format (a single file of its type, or claimed by a later format).

`cannot_read` on a refusal: no second warning (`read` warned, naming format and file with `over its read limit`), no retry and no "did not answer" (the same file gives the same outcome; `did_not_answer` ignores it too). A refusal a format does not catch still ends its call, and the core discards its result as before (`<format> skipped: …`): a bug of that format, visible in the warning.

## D3. The allowlist

`Format.read_limit`, default 1 MiB, a class attribute: a format that needs more declares it, with the reason in a comment, and the number is reviewed with its code. `Directory.inspect` takes the calling format's `read_limit` instead of a `budget` argument, so one number bounds a format's reads through both readers. `common/hdf5links` declares 4 MiB, the value of `links.BUDGET` until now, which goes; its outcome for a file over the limit is unchanged (a warning, the file a plain HDF5 file, not tried again), its wording now `<file> over its read limit of N bytes; not read further`, the marker shared with `d.read`. The flag past 64 KiB applies to `d.read` only: `inspect`'s reads are a library's (h5py lists a real master's links in 483 KB), and the only format that inspects declares its limit.

## D4. Each format's reads during recognition

From the code, per file and call (2026-11-13):

| Format | Read during recognition, per file | Over 64 KiB? | A refused read |
|---|---|---|---|
| core `zarr/zarr` (pre-order) | `zarr.json`, up to 64 KiB, only if listed at 64 KiB or less | no | would end the call (catches only parse errors); cannot happen: one read of at most 64 KiB |
| core `collapse/*` | nothing | no | |
| core `skeleton/acquisition` (never enabled) | 10 bytes of the header | no | ended the call; fixed: skips the file |
| `em/mrc` | 211 bytes (the map word at 208) | no | ended the call; fixed: skips the file |
| `em/de` | 23 bytes of `*info.txt` | no | skips (`cannot_read`) |
| `em/hitachi` | 14 bytes of the `.txt` header | no | skips (`cannot_read`) |
| `em/empad` | 65,536 bytes (64 KiB) of the XML header | at the threshold, not over | skips (catches every exception; its own warning too) |
| `em/dmw` | 16 bytes | no | skips (`dm.header`) |
| `em/dmwx` | 1,054 bytes (local header and a name of up to 1,024 bytes) | no | skips (`dm.header`) |
| `em/k2is` | 16 bytes of a lone `.gtg` | no | skips (`dm.header`) |
| `em/dm3`, `em/dm4`, `em/merlin`, `em/blockfile` | nothing | no | |
| `common/json`, `common/xml` | 64 bytes | no | skips (`cannot_read`) |
| `common/ini` | 1,024 bytes | no | skips (`cannot_read`) |
| other `common/structured` formats, `common/text`, `common/image` | nothing | no | |
| `common/docx` and the other OOXML and ODF packages | 4 bytes | no | skips (`office.head`) |
| `common/legacy` OLE2 types, `common/ole` | 8 bytes | no | skips (`office.head`) |
| `common/pdf` | 5 bytes, and 1,024 more when `%PDF-` is not at the start: 1,029 | no | skips (`office.head`) |
| `common/npz` | 4 bytes | no | skips (`values.start`) |
| `common/nexus` | 8 bytes | no | skips (`values.start`) |
| `common/hspy` | 4,096 bytes | no | skips (`values.start`) |
| `common/matlab`, `common/notebook`, `common/pickle` | 6, 64 and 2 bytes | no | skips (`values.start`) |
| `common/npy`, `common/hdf5`, `common/python` | nothing | no | |
| `common/hdf5links` | through `inspect`, h5py's reads, declared 4 MiB (the real master: 483 KB) | by design; not flagged (D3) | the file not listed, as before |
| `common/zarr` (pre-order) | as core `zarr/zarr` | no | as core `zarr/zarr` |
| `common/zspy` (pre-order) | a v3 `zarr.json` twice (core rule, then its root attribute), up to 2 × 64 KiB; a v2 `.zattrs` up to 64 KiB | **yes, when `zarr.json` is over 32 KiB** | skips (`values.start`) for the second read; the first as `zarr/zarr` |

So no format reaches 1 MiB of one file through `d.read` today; one, `common/zspy`, can pass 64 KiB, by reading the same file twice (BACKLOG). Before this change, a refused read ended the call of `em/mrc` and the skeleton (neither caught an `OSError` around its read); both now skip the file, which also makes a read error on one MRC file skip that file instead of discarding `em/mrc`'s result for the folder (the spec's "A read error on one file"). The core `zarr/zarr` still ends its call on a read error of `zarr.json`; it cannot be refused (one read of at most 64 KiB), and changing what a read error does there is outside this change.
