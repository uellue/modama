## REMOVED Requirements

### Requirement: A byte budget bounds every format call
**Reason**: The budget was the folder's: a folder of more than about 4,970 MRC files lost `em/mrc`, the same files in subfolders kept it (@weber, 329: "the limit per folder is arbitrary").
**Migration**: Reads are bounded per file: "A read limit bounds what a format reads of one file", "A file over the read limit is skipped by the format", "A file read past 64 KiB is flagged", "A format may declare a larger read limit".

## ADDED Requirements

### Requirement: A read limit bounds what a format reads of one file
In one format call, the bytes a format reads of one file SHALL be counted, all its reads of that file added, and SHALL NOT pass the format's read limit, 1 MiB unless the format declares more; the number of files in the folder SHALL NOT change what a format may read of each. The core's read of a file's new type after a drop SHALL NOT count (decision 166).

#### Scenario: Many files each within the limit
- **WHEN** a test format reads 60 KiB of each of 20 text files of one folder, 1.2 MiB in all
- **THEN** each file is a dataset of that format, and the crawl warns of nothing

#### Scenario: A flat folder and the same files in 100 subfolders
- **WHEN** a folder holds 10,000 MRC files, and another holds the same files in 100 subfolders of 100
- **THEN** both give 10,000 datasets of `em/mrc` with the same types and bases, and neither has a warning

### Requirement: A file over the read limit is skipped by the format
A read that would take the bytes read of one file past the format's read limit SHALL be refused before it reads, as a read error of that file, and every later read of that file in the call SHALL be refused too. The format SHALL skip the file and keep the rest of its result; the file SHALL stay as it would be without the format; a warning with the marker `over its read limit` SHALL name the format and the file. It SHALL NOT be tried again next crawl.

#### Scenario: A file over the limit among files within it
- **WHEN** a test format reads 1 MiB of `big.txt`, then asks for 1 byte more, then 4, and reads 16 bytes of `small.txt`
- **THEN** `small.txt` is a dataset of that format, `big.txt` a single file of type `text/plain`, the crawl warns once at `big.txt` that it is over the format's read limit of 1048576 bytes, and the folder is not recognised again next crawl

#### Scenario: A real format goes on with its next file
- **WHEN** `em/mrc`'s read limit is set to 100 bytes and it recognises a folder of two MRC files, reading 211 bytes of each
- **THEN** both are single files of type `application/x.mrc`, each with a warning naming `em/mrc` and the file, and no warning that `em/mrc` was skipped

#### Scenario: A refusal the format does not catch
- **WHEN** a test format asks for 1 MiB and 1 byte of a file without catching the refusal
- **THEN** its whole result for the folder is discarded, with the warning `<format> skipped: …`, as for any exception out of a format call

### Requirement: A file read past 64 KiB is flagged
When a format's first bytes reads of one file in one call add up to more than 64 KiB, within its read limit, the read SHALL succeed and the crawl SHALL warn once at the file, naming the format and the file, with the marker `read more than 64 KiB`.

#### Scenario: Reads at, past and adding up to more than 64 KiB
- **WHEN** a test format reads 64 KiB of `at.txt`, 64 KiB and one byte of `past.txt`, and 40 KiB twice of `twice.txt`
- **THEN** all three are datasets of that format, and the crawl warns `read more than 64 KiB` at `past.txt` and at `twice.txt`, once each, and not at `at.txt`

### Requirement: A format may declare a larger read limit
A format SHALL be able to declare a larger read limit than 1 MiB, an explicit number in its code; that limit SHALL bound both its first bytes reads and its inspections of each file.

#### Scenario: A format that declares 2 MiB
- **WHEN** a test format that declares a read limit of 2 MiB reads 1 MiB of a file twice
- **THEN** the file is a dataset of that format, with the one warning `read more than 64 KiB`

#### Scenario: An inspecting format's limit
- **WHEN** `common/hdf5links`, whose read limit is set to 1000 bytes, lists the links of a master that needs more
- **THEN** the master is a plain HDF5 dataset with the warning `over its read limit of 1000 bytes; not read further`, not marked `not inspected`

## MODIFIED Requirements

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and bounded readers for the directory's own files (a file's first bytes, and the inspection of a file in a worker process), and SHALL NOT receive database connections or access to other directories. Both readers SHALL open a file without following a symlink and only if it is a regular file. The bytes the core reads to find a file's new type, after a format said the file is not of its name's type, SHALL NOT count against that format's read limit (decision 166); the format's own reads do.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the number of bytes it asked for, and the read counts against the format's read limit for that file

#### Scenario: An entry replaced by a symlink is not read for its first bytes
- **WHEN** a format reads the first bytes of an entry listed as a regular file that has become a symlink since the listing
- **THEN** nothing is read through the symlink, and the format gets the error of a file it cannot read

#### Scenario: The new type's detection does not use the format's budget
- **WHEN** `test/tags`, with a read limit of 1,000 bytes, reads the first 4 bytes of `big.tags`, 20,000 bytes of text, and says it is not of its type
- **THEN** `big.tags` is a single file of type `text/plain`, and no warning about `test/tags`'s reads is given
