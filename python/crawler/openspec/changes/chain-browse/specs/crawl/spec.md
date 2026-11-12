## ADDED Requirements

### Requirement: One folder is recognised as in the crawl of the whole tree
The walk SHALL accept a folder `top`, relative to the root; it SHALL then run the pre-order call of every folder from the root down to `top`, return the dataset of the first one that collapses, and otherwise recognise `top` alone, as the crawl does but without its subfolders' datasets, and SHALL NOT list or read anything below `top`'s subfolders. When `top` or a folder on the way is excluded, not a folder, or a symlink, the result SHALL have no datasets. Without `top`, the walk SHALL be unchanged (change `chain-browse`, design D5).

#### Scenario: The same datasets as the whole crawl
- **WHEN** a fixture tree is walked whole and walked with `top` set to one of its folders, with formats that adopt nothing
- **THEN** the datasets recognised in that folder are equal in both results

#### Scenario: Subfolders are not entered
- **WHEN** `top` has a subfolder with files
- **THEN** nothing in the subfolder is listed or read

#### Scenario: A folder inside a collapsed tree
- **WHEN** the walk's `top` is a folder inside a Zarr store
- **THEN** the result is the store's one collapsed dataset, and nothing below the store was read

#### Scenario: An excluded folder
- **WHEN** `top` is under a folder the crawl excludes
- **THEN** the result has no datasets
