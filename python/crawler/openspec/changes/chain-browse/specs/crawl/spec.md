## ADDED Requirements

### Requirement: A subtree is recognised as in the crawl of the whole tree
The walk SHALL accept a folder `top`, relative to the root; it SHALL then run the pre-order call of every folder from the root down to `top`'s parent, return the dataset of the first one that collapses, and otherwise walk `top`'s subtree, with paths relative to the root and the crawl's exclusions and per-path ignores. When `top` or a folder on the way is excluded, not a folder, or a symlink, the result SHALL have no datasets. Without `top`, the walk SHALL be unchanged (change `chain-browse`, design D5).

#### Scenario: The same datasets as the whole crawl
- **WHEN** a fixture tree is walked whole and walked with `top` set to one of its folders
- **THEN** the datasets anchored under that folder are equal in both results

#### Scenario: A folder inside a collapsed tree
- **WHEN** the walk's `top` is a folder inside a Zarr store
- **THEN** the result is the store's one collapsed dataset, and nothing below the store was read

#### Scenario: An excluded folder
- **WHEN** `top` is under a folder the crawl excludes
- **THEN** the result has no datasets
