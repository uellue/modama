## ADDED Requirements

### Requirement: The file's text as the second description
A record whose dataset's extracted values hold `text`, a non-empty string, SHALL carry it, as stored, as its second `dc:description`, after the summary and in place of the tag lines (requirement "The file's tags go into a second description", change `tags-in-the-record`). A record whose values hold no `text`, or an empty one, SHALL keep the tag lines. A record built from a stored extraction SHALL equal the one built from the extraction that ran.

#### Scenario: A text in place of the tag lines
- **WHEN** a dataset's extracted values hold `text` `{"a": 1, "b": "x"}` and `original_metadata` with `a` 1 and `b` `x`
- **THEN** its record has two `dc:description`: the summary first, then `{"a": 1, "b": "x"}`, and no line `a: 1`

#### Scenario: A text over several lines
- **WHEN** a dataset's `text` is `run 1: tilt series, 1 degree steps\n1-10: focus series, 2 nm steps`
- **THEN** its second `dc:description` holds both lines, separated by a line feed, as stored

#### Scenario: No text, the tag lines as before
- **WHEN** a dataset's values hold `original_metadata` and no `text`, or `text` `""`
- **THEN** its second `dc:description` holds the tag lines, as requirement "The file's tags go into a second description" says

#### Scenario: The same record from a stored extraction
- **WHEN** a dataset with a `text` is crawled, and crawled again with its extraction reused
- **THEN** both crawls build the same record, and the record keeps its datestamp
