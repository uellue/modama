# Spec Delta

## Purpose

Classifying single files by MIME type with a per-deployment database built only from the enabled collections' definitions, following the shared-mime-info checking order.

## ADDED Requirements

### Requirement: The database is built from enabled collections only
The MIME database used for classification SHALL be built from the XML definitions of the enabled collections, and SHALL NOT include definitions installed on the host system.

#### Scenario: A host definition is ignored
- **WHEN** the host system defines a type for `*.foo` and no enabled collection does
- **THEN** a file `x.foo` is classified by content or as the fallback type, not as the host's type

### Requirement: Upstream definitions are part of the core collection
The core collection SHALL ship the freedesktop shared-mime-info definitions as a vendored file with its licence notice, so that common types are recognised without any host dependency.

#### Scenario: PNG is recognised from the vendored definitions
- **WHEN** only the core collection is enabled
- **THEN** a PNG file is classified as `image/png`

### Requirement: Names decide, content resolves
Classification SHALL follow the shared-mime-info checking order: name rules by weight and then longest pattern; content sniffing only when no name rule matches or several types match equally; a name match that is a subclass of the sniffed type wins.

#### Scenario: Longest pattern wins
- **WHEN** a file named `a.tar.gz` is classified
- **THEN** its type is `application/x-compressed-tar`

#### Scenario: Unknown name is sniffed
- **WHEN** a file has no extension and starts with the PNG signature
- **THEN** its type is `image/png`

### Requirement: Ties resolve to the common ancestor
When two candidate types remain equally good, the result SHALL be their nearest common ancestor in the subclass hierarchy, and the tie SHALL be reported; only candidates with no common ancestor other than the fallback SHALL resolve to the fallback.

#### Scenario: Two HDF5 subtypes
- **WHEN** a file matches two name rules of equal weight whose types are both subclasses of `application/x-hdf5` and content does not decide
- **THEN** its type is `application/x-hdf5` and a warning names both candidates

### Requirement: Fallback types
A file that matches nothing SHALL be `text/plain` if its first bytes look like text and `application/octet-stream` otherwise, regardless of its permission bits.

#### Scenario: Executable binary without extension
- **WHEN** a file with the executable bit set contains binary data and matches no rule
- **THEN** its type is `application/octet-stream`
