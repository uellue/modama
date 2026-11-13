## ADDED Requirements

### Requirement: A format may inspect files of its folder in worker processes
The core SHALL let a format run a function of its own on files of its folder in one pool of worker processes per crawl, one folder at a time, each file opened without following a symlink and only if it is a regular file, through a read-only file object with a byte budget per file, closed after the function returns, with a time limit per file enforced from outside the worker; it SHALL return one outcome per file.

#### Scenario: Reading a file at any offset within the budget
- **WHEN** a format inspects an entry with a function that reads 100 bytes at its end and 100 at its start, with a budget of 1 KiB
- **THEN** the function's result comes back, and the file's outcome says 200 bytes were read

#### Scenario: An entry replaced by a symlink or a FIFO after the listing is not read
- **WHEN** a format inspects two entries listed as regular files, of which one has become a symlink to a file outside the folder and the other a FIFO since the listing
- **THEN** neither is read, the call does not block, and each outcome says it is not a regular file

#### Scenario: A read error inside an inspection
- **WHEN** a read of the file object fails with an I/O error and the function catches the error its library made of it
- **THEN** the outcome says the file system did not answer, and the folder's stored datasets are kept, as for any read the file system did not answer

#### Scenario: A budget breach stays raised
- **WHEN** a function reads past its file's budget, catches the error, and reads again
- **THEN** the second read raises too, and the outcome says the file is over its budget

#### Scenario: An inspection that fails
- **WHEN** a function raises an exception of its own
- **THEN** the outcome says it failed, with the exception, and the folder is recognised again next crawl

#### Scenario: An inspection that hangs
- **WHEN** a function does not return within the time limit
- **THEN** its worker is killed, the outcome says it timed out, the other files' inspections end as before, and the folder is recognised again next crawl

#### Scenario: An inspection that crashes its process
- **WHEN** a function ends its worker process (a crash in a library)
- **THEN** the outcome says the process died, the crawl goes on, and the folder is recognised again next crawl

#### Scenario: One pool for the crawl
- **WHEN** a crawl inspects files in 20 folders on 32 walk threads
- **THEN** at most one pool of worker processes exists at any time, and a crawl that inspects nothing starts none

## MODIFIED Requirements

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and bounded readers for the directory's own files (a file's first bytes, and the inspection of a file in a worker process), and SHALL NOT receive database connections or access to other directories. Both readers SHALL open a file without following a symlink and only if it is a regular file.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the configured number of bytes and the read counts against the directory's budget

#### Scenario: An entry replaced by a symlink is not read for its first bytes
- **WHEN** a format reads the first bytes of an entry listed as a regular file that has become a symlink since the listing
- **THEN** nothing is read through the symlink, and the format gets the error of a file it cannot read
