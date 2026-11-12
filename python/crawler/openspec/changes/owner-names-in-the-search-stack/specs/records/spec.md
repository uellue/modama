## MODIFIED Requirements

### Requirement: Dublin Core mapping
A record's `oai_dc` SHALL carry the anchor path as title, the owner's user name as creator, the newest member mtime as date, `Dataset` as type, the dataset's MIME type as format, the browse URL as identifier, and `ER-C` as publisher. The user name SHALL be the login name that the system's user database gives for the owner's uid (in the search stack: the directory, through sssd); an owner without a name there SHALL be the uid as a decimal number.

#### Scenario: Single file
- **WHEN** a text file owned by user `alice` is a dataset
- **THEN** its record has `dc:title` equal to the path, `dc:creator` `alice`, `dc:format` `text/plain` and `dc:type` `Dataset`

#### Scenario: An owner without a name
- **WHEN** a file owned by uid 4242, which the user database does not know, is a dataset
- **THEN** its record has `dc:creator` `4242`

#### Scenario: An owner from the directory, in the search stack
- **WHEN** in the search stack's test deployment a file is owned by uid 10001, which only the test directory knows (as `alice`), and is crawled
- **THEN** its record has `dc:creator` `alice`, and so do the warehouse's record and the index's `creators`
