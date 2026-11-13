## ADDED Requirements

### Requirement: A format may inspect files of its folder in worker processes
The core SHALL let a format run a function of its own on files of its folder in worker processes, each file opened without following a symlink and only if it is a regular file, through a read-only file object whose reads count against the call's byte budget, closed after the function returns, with a time limit per file enforced from outside the worker; it SHALL return one outcome per file.

#### Scenario: Reading a file at any offset within the budget
- **WHEN** a format inspects an entry with a function that reads 100 bytes at its end and 100 at its start
- **THEN** the function's result comes back, and 200 bytes count against the call's budget

#### Scenario: An entry replaced by a symlink or a FIFO after the listing is not read
- **WHEN** a format inspects two entries listed as regular files, of which one has become a symlink to a file outside the folder and the other a FIFO since the listing
- **THEN** neither is read, the call does not block, and each outcome says it is not a regular file

#### Scenario: A read error inside an inspection
- **WHEN** a read of the file object fails with an I/O error and the function catches the error its library made of it
- **THEN** the outcome says the file system did not answer, and the folder's stored datasets are kept, as for any read the file system did not answer

#### Scenario: A budget breach stays raised
- **WHEN** a function reads past the budget, catches the error, and reads again
- **THEN** the second read raises too, and the format's result for the folder is discarded with a warning naming the format

#### Scenario: An inspection that hangs
- **WHEN** a function does not return within the time limit
- **THEN** its worker is killed, the outcome says it timed out, the folder's stored datasets are kept, and the other files' inspections end as before

#### Scenario: An inspection that crashes its process
- **WHEN** a function ends its worker process (a crash in a library)
- **THEN** the outcome says the process died, the folder gets a warning naming the file, and the crawl goes on

## MODIFIED Requirements

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and bounded readers for the directory's own files (a file's first bytes, and the inspection of a file in a worker process), and SHALL NOT receive database connections or access to other directories.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the configured number of bytes and the read counts against the directory's budget

### Requirement: A byte budget bounds every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading, its inspections in worker processes included; exceeding it SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl. The budget SHALL be the core's (1 MiB), unless the format declares a larger one, which its spec justifies.

#### Scenario: A format reads past its budget
- **WHEN** a format reads more bytes on a directory than its budget allows
- **THEN** its result is discarded, the directory is recognised by the remaining formats, and a warning names the format and the read

#### Scenario: A format with a budget of its own
- **WHEN** a format that declares a budget of 4 MiB reads 2 MiB of a directory's files, and another format without a declaration reads 2 MiB
- **THEN** the first format's result stands, the second's is discarded with a warning naming it
