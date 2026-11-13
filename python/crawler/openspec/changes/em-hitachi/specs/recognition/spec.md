## MODIFIED Requirements

### Requirement: Formats run in priority order with exclusive claims
Formats SHALL run in descending priority, ties broken by format id, and an entry or child dataset claimed by a dataset SHALL NOT be available to formats that run later: `Directory.of_type` SHALL NOT return an entry that a format which ran earlier on the directory claimed. A later claim on an already claimed entry (one a format found by name or among all entries) SHALL be reported as a warning.

#### Scenario: Higher priority wins a shared file
- **WHEN** two formats would each build a dataset from the same entry, the later one finding it by name (`Directory.entry`)
- **THEN** the dataset of the higher-priority format exists, the other does not, and a warning names both

#### Scenario: A claimed file is not offered by type
- **WHEN** a format claims a TIFF and a `.txt` of a directory, and a single-file format of `image/tiff` and one of `text/plain` run after it
- **THEN** their `of_type` returns neither file, they build no dataset of them, and the crawl has no warning about them

#### Scenario: Files nobody claimed are still offered
- **WHEN** a format claims one of two TIFFs of a directory
- **THEN** a single-file format of `image/tiff` that runs after it is offered the other TIFF and builds its dataset
