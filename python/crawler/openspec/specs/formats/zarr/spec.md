# formats/zarr Specification

## Purpose

Zarr stores as single datasets: a directory marked as a Zarr v2 or v3 node is the dataset, its chunks are never visited, and a store inside a store belongs to the outer one.

## Requirements

### Requirement: A Zarr store is one collapsed dataset
A directory containing a `zarr.json` (v3) or a `.zarray` or `.zgroup` (v2) SHALL be recognised from its listing as one collapsed dataset of type `application/x-zarr`, and nothing below it SHALL be visited.

#### Scenario: Array store
- **WHEN** a Zarr v3 array written by the Zarr library is crawled
- **THEN** the result has one collapsed dataset anchored at the store and no datasets for its chunk files

#### Scenario: Version 2 group store
- **WHEN** a Zarr v2 group with `.zgroup` and `.zattrs` containing an array directory with `.zarray` is crawled
- **THEN** the result has one collapsed dataset anchored at the group store

### Requirement: Nested stores belong to the outer store
When a Zarr store contains another Zarr store, only the outer store SHALL appear in the result.

#### Scenario: Group containing an array
- **WHEN** a Zarr group store contains an array store as a subdirectory
- **THEN** the result has one dataset, anchored at the group store

### Requirement: Broken stores are reported
A directory that looks like a Zarr store but whose `zarr.json` cannot be parsed SHALL still be collapsed, with a warning naming the problem.

#### Scenario: Corrupt metadata
- **WHEN** a store's `zarr.json` is not valid JSON
- **THEN** the result has one collapsed dataset for it with a warning
