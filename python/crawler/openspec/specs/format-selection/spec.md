# format-selection Specification

## Purpose

Finding installed format collections and selecting, per deployment, which formats run and where, with semantics that admins know from linters.

## Requirements

### Requirement: Collections are discovered through entry points
Installed collections SHALL be discovered through the `modama.formats` entry-point group; a collection name that is registered twice SHALL be rejected when loading, with a message naming both distributions.

#### Scenario: Two collections with the same name
- **WHEN** two installed distributions register the same collection name
- **THEN** loading fails with an error naming both, and no crawl starts

### Requirement: Selection by id with prefixes
The configuration SHALL accept `select` and `ignore` lists of ids, where an id is a collection name, `collection/format`, or `ALL` for every installed format; a collection name SHALL stand for all its formats, including formats added by a later version of the collection.

#### Scenario: Whole collection, one exception
- **WHEN** the configuration has `select = ["gatan"]` and `ignore = ["gatan/dm3-legacy"]`
- **THEN** every format of `gatan` except `dm3-legacy` is enabled

### Requirement: A collection id covers its MIME definitions
Selecting or ignoring a collection by name SHALL also decide whether its MIME definitions are built into the database; ignoring one of its formats SHALL leave the definitions in place. A collection without Python formats, such as `core`, is selected this way.

#### Scenario: Only the common files
- **WHEN** `records --select core PATH` is run
- **THEN** files are classified with the core definitions only and no Python format runs

#### Scenario: A collection switched off as a whole
- **WHEN** `records --ignore em PATH` is run on an EMPAD pair (collection `em`, package `modama-formats-em`)
- **THEN** the raw file is not classified as `application/x.empad-raw`

### Requirement: Unknown ids are rejected
An id in `select`, `ignore` or a per-path ignore that names neither an installed collection nor an installed format SHALL be an error naming the id and the installed ids, before anything is crawled; a typo SHALL NOT silently change what runs.

#### Scenario: Misspelled id on the command line
- **WHEN** `records --select nosuch PATH` is run
- **THEN** standard error names `nosuch`, the exit status is non-zero and nothing is written to standard output

#### Scenario: Misspelled id in the configuration
- **WHEN** the configuration file has `ignore = ["collapse/vnev"]`
- **THEN** the command fails the same way

### Requirement: More specific wins, ignore wins ties
When `select` and `ignore` overlap, the more specific id SHALL override the less specific one, and `ignore` SHALL take precedence over `select` when the same id appears in both.

#### Scenario: Re-enabling one format of an ignored collection
- **WHEN** the configuration has `select = ["gatan/dm4"]` and `ignore = ["gatan"]`
- **THEN** only `gatan/dm4` is enabled

### Requirement: Per-path ignores only subtract
The configuration SHALL accept a mapping from gitignore-style path patterns to lists of ids; for matching paths those formats SHALL NOT run, while the paths are still crawled and classified. A per-path entry SHALL NOT enable a format.

#### Scenario: A reader kept away from a directory
- **WHEN** `per-path-ignores` maps `/legacy/**` to `["zarr/zarr"]`
- **THEN** files under `/legacy` are classified by name and the Zarr format never reads them

#### Scenario: Every format kept away
- **WHEN** `per-path-ignores` maps `/scratch/**` to `["ALL"]`
- **THEN** no Python format runs under `/scratch`, and files there are still classified by name

### Requirement: Crawl exclusions
The configuration SHALL accept patterns of paths that are not crawled at all, with gitignore semantics: a slash at the start or in the middle anchors the pattern at the root, a trailing slash matches directories only, `!` negates, and the last matching pattern wins.

#### Scenario: Patterns copied from a .gitignore
- **WHEN** `exclude` contains `foo/bar`, `build/` and `*.txt` followed by `!keep.txt`
- **THEN** `/foo/bar` is excluded but `/x/foo/bar` is not, a directory `build` is excluded but a file named `build` is not, and `keep.txt` stays in the crawl

#### Scenario: Scratch space excluded
- **WHEN** `exclude` contains `/scratch/**`
- **THEN** nothing under `/scratch` appears in the result
