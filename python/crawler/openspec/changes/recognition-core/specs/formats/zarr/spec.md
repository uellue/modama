# Spec Delta

## Purpose

Zarr stores as single datasets: a directory marked as a Zarr v3 node is the dataset, its chunks are never visited, and a store inside a store belongs to the outer one.

## ADDED Requirements

### Requirement: A Zarr v3 store is one collapsed dataset
A directory containing a `zarr.json` SHALL be recognised from its listing as one collapsed dataset of type `application/x-zarr`, and nothing below it SHALL be visited.

#### Scenario: Array store
- **WHEN** a Zarr v3 array written by the Zarr library is crawled
- **THEN** the result has one collapsed dataset anchored at the store and no datasets for its chunk files

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
