# Design

## Context

See proposal.md, Why. The DM types in `dm/dm.xml` have magic and no globs, on purpose (a misnamed `.dm4` is typed by content). The crawler's MIME detection follows the shared-mime-info order (spec `mime-database`, "Names decide, content resolves"): a name rule decides, and a name match that is a subclass of the sniffed type wins. No core type has a `*.dmw`, `*.gtg` or `*.bin` glob (checked in `formats/core/freedesktop.org.xml` and `er-c.xml`). The Merlin part (`merlin/`) is the pattern for an acquisition of a header and frame files: types for both, a recognizer that groups by stem, a warning for frames without a header.

## Goals / Non-Goals

**Goals:** honest types for `.dmw` and `.gtg`; one dataset per K2IS capture; the tags of a K2IS `.gtg` in its description.
**Non-Goals:** K2IS frame counts or data; `.dmw` metadata; LiberTEM as a dependency.

## Decisions

**D1. Types by name, as subclasses of DM4.** `application/x.dm-dmw` (glob `*.dmw`, in `dm/dm.xml`) and `application/x.dm-gtg` (glob `*.gtg`, in `k2is/k2is.xml`, since the K2IS part reacts to it and each part is tested with its own definitions plus the core's), each `sub-class-of application/x.dm4`. The name decides; content would say DM4, and the name match, being its subclass, wins. The DM4 format reacts to `application/x.dm4` only, so neither type is extracted as an image. Comments say what is verified: "Gatan Digital Micrograph .dmw file" and "Gatan Digital Micrograph .gtg tag file" (LiberTEM calls it "the .gtg file"; Gatan's own names to be confirmed, open question).
*Alternative:* a content rule (no `ImageList` tag): the tag tree is not at a fixed offset, so magic cannot see it; the extractor would have to type files, which is recognition's job.

**D2. K2IS sector files by content.** `application/x.k2is-sector` with magic (priority 60): `big32` `0xFFFF0055` at 0, `big16` 256 at 20, `big16` 1860 at 22, LiberTEM's `DataBlock.is_valid` (the block header layout `header_dtype`: sync, 4 bytes padding, version, flags, 6 bytes padding, block count, then width and height). No glob: `*.bin` is everybody's.

**D3. Grouping as LiberTEM does, with two steps away from it.** In a new part `k2is/`: for each `.gtg` (longest stem first, as Merlin), the sector files whose names start with the `.gtg` file's stem (`X_.gtg` takes `X_*.bin`); exactly 8 make a dataset anchored at the `.gtg` (`NUM_SECTORS`); otherwise nothing is claimed, and a `.gtg` with some sector files gets a warning that names it and their number ("X_.gtg: 7 sector files X_*.bin, a K2IS acquisition has 8"). Sector files of no `.gtg`: one warning per directory, as Merlin's orphans. A `.gtg` without sectors stays a single file, no warning (configuration files like `IDES_DMS_Config.gtg` exist). Away from LiberTEM (review finding 3, decision 130): (a) a sector file belongs to the longest stem it starts with, whether that stem has 8 sector files or not, so that an incomplete `scan_2_.gtg` does not break a complete `scan_.gtg` next to it (LiberTEM would glob `scan_*.bin`, find 15 and refuse `scan_.gtg`). The price: a `.gtg` whose stem starts a sector name of another (`X_1.gtg` next to `X_.gtg` with `X_1.bin` to `X_8.bin`) takes that sector, and neither forms a capture, with a warning for each; not seen. (b) `.bin`, like `.gtg` (shared-mime-info globs ignore case), in any case: LiberTEM lower-cases the extension of the path it is given, and globs `*.bin` case-sensitively on Linux but not on Windows, where Gatan Microscopy Suite writes the files; whether it writes `.BIN` is not known.

**D4. Extraction from the `.gtg` tags only.** RosettaSciIO's `DigitalMicrographReader` on our own handle (64 KiB buffer, readahead off, as `dm.first_image` on branch `dm-handle`), `parse_file`, then the tag tree, without image dictionaries (a `.gtg` may have none). The description gives, where present, the tags LiberTEM reads for the scan shape (`SI Dimensions` `Size X`, `Size Y`) and the `Microscope Info` voltage and name, under the tag names and with the values as the reader gives them (README, "Values and units"), for example `SI Dimensions.Size X 64`; the number of files and their size are in the basic description already. Subjects: the display name "Gatan K2 IS" and the microscope name if present (a string tag `Name` in `Microscope Info`, as LiberTEM does not read it: to be checked on a real `.gtg`).
*Alternative:* the 4D-STEM subject as EMPAD has it when a scan exists: only if the tags show a scan; decided with the representative file.

## Risks / Trade-offs

- [The tag names are LiberTEM's, not checked on a real `.gtg` here] → the representative fixture decides; until then the extractor's test runs on a reproducer, and missing tags are left out, not guessed.
- [A `.dmw` that does hold an image is no longer extracted] → none seen: all 2,036 on staging failed for lack of an `ImageList`.
- [Fixtures] → no real K2IS capture or `.dmw` in the VM; reproducers are cut or built (a DM4 file of RosettaSciIO's test data renamed, sector files with valid block headers); representative files from staging need @weber's agreement per file (task 3.1).
