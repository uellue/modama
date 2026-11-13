# Spec Delta

## ADDED Requirements

### Requirement: A collapsed directory is stamped with what its format reads below it
A collapsed dataset's stamp SHALL be its directory's listing and, where its format gives one, a digest of the files below the directory that the format's extractor reads; it SHALL be computed at every crawl, also for a directory taken over with an unchanged listing, so that a change of such a file makes the dataset extracted again. A format whose digest fails SHALL give a warning naming it and a fixed marker in place of the digest; the crawl goes on.

#### Scenario: A file deep below a collapsed directory changes
- **WHEN** a file two folders below a collapsed directory, which its format names in its digest, is rewritten in place between two crawls, so that no listing changes
- **THEN** the second crawl takes the directory over without recognising it, and the collapsed dataset's stamp differs from the first crawl's

#### Scenario: A failing collapsed state
- **WHEN** a format's digest of the files below its collapsed directory raises an exception, on two crawls
- **THEN** both crawls end, each with a warning naming the format, the dataset has the same stamp on both, and it differs from the stamp of the listing alone
