# Spec Delta

## Purpose

Finding installed format collections and selecting, per deployment, which formats run and where, with semantics that admins know from linters.

## ADDED Requirements

### Requirement: Collections are discovered through entry points
Installed collections SHALL be discovered through the `modama.formats` entry-point group; a collection name that is registered twice SHALL be rejected when loading, with a message naming both distributions.

#### Scenario: Two collections with the same name
- **WHEN** two installed distributions register the same collection name
- **THEN** loading fails with an error naming both, and no crawl starts

### Requirement: Selection by id with prefixes
The configuration SHALL accept `select` and `ignore` lists of ids, where an id is a collection name or `collection/format`; a collection name SHALL stand for all its formats, including formats added by a later version of the collection.

#### Scenario: Whole collection, one exception
- **WHEN** the configuration has `select = ["gatan"]` and `ignore = ["gatan/dm3-legacy"]`
- **THEN** every format of `gatan` except `dm3-legacy` is enabled

### Requirement: More specific wins, ignore wins ties
When `select` and `ignore` overlap, the more specific id SHALL override the less specific one, and `ignore` SHALL take precedence over `select` when the same id appears in both.

#### Scenario: Re-enabling one format of an ignored collection
- **WHEN** the configuration has `select = ["gatan/dm4"]` and `ignore = ["gatan"]`
- **THEN** only `gatan/dm4` is enabled

### Requirement: Per-path ignores only subtract
The configuration SHALL accept a mapping from gitignore-style path patterns to lists of ids; for matching paths those formats SHALL NOT run, while the paths are still crawled and classified. A per-path entry SHALL NOT enable a format.

#### Scenario: A reader kept away from a directory
- **WHEN** `per-path-ignores` maps `/legacy/**` to `["empad"]`
- **THEN** files under `/legacy` are classified by name and the EMPAD format never reads them

### Requirement: Crawl exclusions
The configuration SHALL accept gitignore-style patterns of paths that are not crawled at all.

#### Scenario: Scratch space excluded
- **WHEN** `exclude` contains `/scratch/**`
- **THEN** nothing under `/scratch` appears in the result
