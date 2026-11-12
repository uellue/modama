# records Specification

## Purpose

Turning a dataset of the recognition result into its OAI-PMH record: identifier, browse URL, Dublin Core elements, datestamp, and the `oai_dc` rendering that the server and the command line share.

## Requirements

### Requirement: One record per dataset
Every dataset of the recognition result SHALL produce exactly one record, including single-file datasets and collapsed datasets.

#### Scenario: Collapsed tree yields one record
- **WHEN** a directory is a collapsed dataset
- **THEN** one record exists for it and none for the files below it

### Requirement: Identifiers derive from the anchor path
The OAI identifier SHALL be `oai:er-c-data-mgmt.fz-juelich.de:` followed by the anchor path quoted like the browse URL with `:` escaped; local parts of 255 characters or more SHALL be shortened to exactly 255 characters with a hash suffix. The `dc:identifier` SHALL be the anchor's browse URL.

#### Scenario: Short path
- **WHEN** the anchor is `/adhoc/livecalibration/generate.ipynb`
- **THEN** the identifier is `oai:er-c-data-mgmt.fz-juelich.de:/adhoc/livecalibration/generate.ipynb` and `dc:identifier` is `https://er-c-data-mgmt.fz-juelich.de/browse/?path=/adhoc/livecalibration/generate.ipynb`

#### Scenario: Long path
- **WHEN** the quoted anchor path is 300 characters long
- **THEN** the identifier's local part is 255 characters, ends in `~` and hex digits, and differs for paths that differ only at the end

### Requirement: Dublin Core mapping
A record's `oai_dc` SHALL carry the anchor path as title, the owner's user name as creator, the newest member mtime as date, `Dataset` as type, the dataset's MIME type as format, the browse URL as identifier, and `ER-C` as publisher.

#### Scenario: Single file
- **WHEN** a text file owned by user `alice` is a dataset
- **THEN** its record has `dc:title` equal to the path, `dc:creator` `alice`, `dc:format` `text/plain` and `dc:type` `Dataset`

### Requirement: Collections reference their member datasets
A dataset whose parts are datasets SHALL carry a `dc:relation` with the browse URL of each such part; a part SHALL carry a `dc:relation` with the browse URL of its parent.

#### Scenario: Parent and part
- **WHEN** a collection dataset adopts a child dataset
- **THEN** the collection's record lists the child's browse URL under `dc:relation`, and the child's record lists the collection's

### Requirement: The datestamp moves when the record changes
A record's datestamp SHALL be the time its content last changed, truncated to seconds, and SHALL NOT change on a crawl that produces the same content.

#### Scenario: Unchanged crawl
- **WHEN** a tree is crawled twice without changes
- **THEN** every record keeps its datestamp

### Requirement: Rendering is valid oai_dc
The rendered record SHALL validate against the OAI-PMH and `oai_dc` schemas, and characters that XML cannot carry SHALL be replaced.

#### Scenario: Control character in a name
- **WHEN** a member path contains a control character
- **THEN** the rendering validates and shows the replacement character in its place
