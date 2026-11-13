# Spec Delta

## MODIFIED Requirements

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and a bounded reader for the directory's own files, and SHALL NOT receive database connections or access to other directories. The reader SHALL give a file's first bytes, or a read-only file object of the file, unbuffered and with readahead off, whose reads at any offset count against the directory's budget, so that a library that reads a file's structure (h5py) can be handed it.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the configured number of bytes and the read counts against the directory's budget

#### Scenario: Reading a file at any offset within the budget
- **WHEN** a format opens an entry through the reader and reads 100 bytes at its end and 100 at its start
- **THEN** it receives the bytes, and 200 bytes count against the directory's budget

#### Scenario: A library that swallows the budget's error
- **WHEN** a format hands the reader's file object to a library that catches the error of a read past the budget and raises its own, and the format catches that
- **THEN** the format's result for the directory is discarded with a warning naming the format, as for any read past the budget

### Requirement: Budgets bound every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading, and a time limit, checked after the call returns (isolating a format that hangs is deferred to worker subprocesses, architecture G); exceeding either SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl. The byte budget SHALL be the core's (1 MiB), unless the format declares a larger one, which it SHALL justify in its spec.

#### Scenario: A slow format's result is discarded
- **WHEN** a format takes longer than the time limit on a directory
- **THEN** its result is discarded, the directory is recognised by the remaining formats, and a warning names the format, the time it took and the limit

#### Scenario: A format with a budget of its own
- **WHEN** a format that declares a budget of 4 MiB reads 2 MiB of a directory's files, and another format without a declaration reads 2 MiB
- **THEN** the first format's result stands, the second's is discarded with a warning naming it
