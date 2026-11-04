# recognition Specification

## Purpose

How formats declare themselves and how the core runs them on a directory to produce datasets: the interface, the order, membership, the result, and its budgets.

## Requirements

### Requirement: A format declares what it is
A format SHALL declare the MIME type of the datasets it produces, a priority from 0 to 100, the types or the directory kind it reacts to, and whether it is a collection type, and SHALL provide one recognition function that receives a directory and returns datasets.

#### Scenario: Declaration is visible without running the format
- **WHEN** a collection is loaded
- **THEN** every format's type, priority, reactions and collection flag are available before any directory is recognised

### Requirement: Recognition runs twice per directory
The core SHALL call each enabled format once before descending, with the directory's entry names, sizes and kinds only, and once after its subdirectories are final, with entries, their MIME types, and the subdirectories' datasets. A format that answers in the first call SHALL end the descent.

#### Scenario: A collapse answer stops the descent
- **WHEN** a format returns a collapsed dataset in the first call
- **THEN** no second call is made for that directory and nothing below it is visited

#### Scenario: A sibling format needs types
- **WHEN** a format reacts to a MIME type
- **THEN** it is called in the second call only, and only if an entry of that type is present

### Requirement: Plain data in, no reach outside the directory
A format SHALL receive only the directory's entries, their types, the children's datasets and a bounded reader for the directory's own files, and SHALL NOT receive database connections or access to other directories.

#### Scenario: Reading a file within the budget
- **WHEN** a format reads the first bytes of an entry through the reader
- **THEN** it receives at most the configured number of bytes and the read counts against the directory's budget

### Requirement: Formats run in priority order with exclusive claims
Formats SHALL run in descending priority, ties broken by format id, and an entry or child dataset claimed by a dataset SHALL NOT be available to formats that run later. A later claim on an already claimed entry SHALL be reported as a warning.

#### Scenario: Higher priority wins a shared file
- **WHEN** two formats would each build a dataset from the same entry
- **THEN** the dataset of the higher-priority format exists, the other does not, and a warning names both

### Requirement: Claims stay within the directory
A format SHALL only claim its directory's own entries and whole child datasets, which it adopts as parts of its dataset; a claim on anything else SHALL be rejected with a warning.

#### Scenario: Adopting a child dataset
- **WHEN** a format includes a child dataset in its own dataset
- **THEN** the child's parent is the new dataset and the child's members are unchanged

### Requirement: Unclaimed files become single-file datasets
Every regular file that no format claims SHALL become a dataset of its own MIME type, so that every file outside a collapsed dataset is represented.

#### Scenario: Unknown file
- **WHEN** a file matches no rule and no format claims it
- **THEN** the result contains a dataset of type `application/octet-stream` anchored at that file

### Requirement: The recognition result is one structure
The result of a tree SHALL be a list of datasets, each with type, anchor, sorted members including the anchor, format id and version, basis, warnings, parent and collapsed flag, plus warnings not attributable to a dataset.

#### Scenario: Basis is recorded
- **WHEN** a format recognises a dataset
- **THEN** the dataset carries the format's stated basis for the claim

### Requirement: Nesting is reported unless declared
A dataset SHALL get a parent only through a format declared as a collection type; a parent set by any other format SHALL be reported as a warning.

#### Scenario: Undeclared nesting
- **WHEN** a non-collection format adopts a child dataset
- **THEN** the adoption stands and the result carries a warning naming both datasets

### Requirement: Budgets bound every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading, and a time limit, checked after the call returns (isolating a format that hangs is deferred to worker subprocesses, architecture G); exceeding either SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl.

#### Scenario: A slow format's result is discarded
- **WHEN** a format takes longer than the time limit on a directory
- **THEN** its result is discarded, the directory is recognised by the remaining formats, and a warning names the format, the time it took and the limit
