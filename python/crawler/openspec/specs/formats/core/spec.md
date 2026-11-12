# formats/core Specification

## Purpose

The core collection: the single-file types of common and generic formats, provided by the vendored upstream definitions, so that every deployment has a baseline and every file has a type.

## Requirements

### Requirement: Common single-file types
The core collection SHALL classify common files (images, documents, text, archives, source code) by the vendored shared-mime-info definitions, each as a single-file dataset of its type.

#### Scenario: Mixed directory
- **WHEN** a directory contains a PNG, a JSON file and a Python source file
- **THEN** the result has three single-file datasets of types `image/png`, `application/json` and `text/x-python`

### Requirement: Generic containers stay generic until refined
A file recognised only as a generic container type (XML, JSON, ZIP, HDF5) SHALL keep that type, so that a more specific format from another collection can refine it.

#### Scenario: Plain XML
- **WHEN** an XML file matches no specific rule
- **THEN** its dataset type is `application/xml`
