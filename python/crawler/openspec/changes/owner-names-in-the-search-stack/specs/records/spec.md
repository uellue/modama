## MODIFIED Requirements

### Requirement: Dublin Core mapping
A record's `oai_dc` SHALL carry the anchor path as title, the owner as creator, the newest member mtime as date, `Dataset` as type, the dataset's MIME type as format, the browse URL as identifier, and `ER-C` as publisher. The creator SHALL be the owner's full name, the GECOS field that the system's user database gives for the owner's uid (in the search stack: the directory, through sssd) up to its first comma; the login name when that is empty; the uid as a decimal number when the user database does not know the uid (decision 201).

#### Scenario: Single file
- **WHEN** a text file owned by user `alice`, whose GECOS field is `Alice Anderson`, is a dataset
- **THEN** its record has `dc:title` equal to the path, `dc:creator` `Alice Anderson`, `dc:format` `text/plain` and `dc:type` `Dataset`

#### Scenario: An owner without a full name
- **WHEN** a file's owner has an empty GECOS field, or `,,,`, and the login name `dev`
- **THEN** its record has `dc:creator` `dev`

#### Scenario: An owner without a name
- **WHEN** a file owned by uid 4242, which the user database does not know, is a dataset
- **THEN** its record has `dc:creator` `4242`

#### Scenario: An owner from the directory, in the search stack
- **WHEN** in the search stack's test deployment a file is owned by uid 10001, which only the test directory knows (as `alice`, `cn: Alice Anderson`, primary group `iff`), and is crawled
- **THEN** its record has `dc:creator` `Alice Anderson` and a `dc:description` that ends in `, group iff`, and the warehouse's record and the index's `creators` have `Alice Anderson`

### Requirement: Every record carries a description
Every record SHALL carry one `dc:description`, a readable summary on one line. For a dataset with extracted metadata it SHALL start with the extracted values; otherwise it SHALL state the type's human-readable name, the number of files and their total size, and the folder the dataset is in. After the folder it SHALL name the owner's primary group, `group <name>`, when the user database knows the owner's uid and the name of that user's primary group; otherwise nothing (decision 202).

#### Scenario: A file without an extractor
- **WHEN** a plain text file of 1,234 bytes in `notes/` is a dataset, owned by a user whose primary group is `erc-1`
- **THEN** its record's `dc:description` is `Plain text document, 1 file, 1.2 kB, in notes/, group erc-1`

#### Scenario: A file with extracted metadata
- **WHEN** a dataset's extractor yields an acceleration voltage of 300 kV and a magnification of 50,000
- **THEN** its record's `dc:description` starts with those values, before the type, size, folder and group

#### Scenario: An owner without a known group
- **WHEN** the owner's uid is unknown, or the user's primary gid has no name in the user database
- **THEN** the description ends with the folder, `in notes/`, and names no group
