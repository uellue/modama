# formats/collapse Specification

## Purpose

Directories that are one dataset as a whole and whose contents are not worth indexing: software environments, version control stores, caches.

## Requirements

### Requirement: Environments are collapsed from their listing
The collapse collection SHALL recognise a Python virtual environment, a conda installation or environment, a `node_modules` directory, a `.git` directory, a `.svn` directory, a `__pycache__` directory and an `.ipynb_checkpoints` directory from the directory's listing alone, as one collapsed dataset each.

#### Scenario: Virtual environment
- **WHEN** a directory created by `python -m venv` is crawled
- **THEN** the result has one collapsed dataset anchored at it, of a type naming a Python environment, and no datasets below it

#### Scenario: Subversion working copy
- **WHEN** a working copy's `.svn` directory (`entries`, `format`, `wc.db`, pristine copies `pristine/xx/*.svn-base`) is crawled
- **THEN** the result has one collapsed dataset anchored at the `.svn` directory, of a type naming Subversion, and no datasets below it; the working copy's own files are datasets as usual

#### Scenario: Cache directory
- **WHEN** a `__pycache__` directory with compiled files is crawled
- **THEN** the result has one collapsed dataset anchored at it

### Requirement: Collapsed datasets are recognised before descending
The collapse formats SHALL answer in the pre-order call so that nothing below a collapsed directory is visited.

#### Scenario: Large environment
- **WHEN** an environment contains thousands of files
- **THEN** none of them is listed, classified or opened
