# Spec Delta

## ADDED Requirements

### Requirement: Extraction results are recorded and compared
For each fixture with a dataset of a format with an extractor, the plugin SHALL run the extractor and compare its result (summary, subjects and values, or the error's type) with the result recorded next to the fixture's recognition result, in the same way: a difference fails naming the dataset and the fields that differ, and the regeneration option rewrites the record and fails for each one that changed (decision T4).

#### Scenario: A dependency changes a fixture's output
- **WHEN** the reader a format uses returns another value for a representative fixture than the recorded one
- **THEN** the fixture's test fails naming the dataset and the changed field, with the old and new value

#### Scenario: First run records the extraction
- **WHEN** a fixture of a format with an extractor has no recorded extraction
- **THEN** the extraction is written, the test fails asking for a review, and the next run passes

### Requirement: A recorded extraction error is meant
The plugin SHALL record an extraction error only with a failure that says so, and never for a reproducer whose validity is not `invalid-by-design`: a reproducer of a bug records the fixed result (hallway test of 2026-11-13, G15: a red first run on a bug would record the bug as expected).

#### Scenario: First run records an extraction error
- **WHEN** a fixture without a recorded result fails extraction, and it is not a reproducer or its validity is `invalid-by-design`
- **THEN** the error's type is written, and the test fails saying that it recorded an ERROR as the expected result, intended only for a fixture that is invalid-by-design, and that for a reproducer the file is to be deleted and the code fixed first

#### Scenario: A reproducer's error is not recorded
- **WHEN** the extraction of a reproducer fixture whose validity is not `invalid-by-design` fails, on its first run or with regeneration
- **THEN** nothing is written, and the test fails naming the dataset and the error and asking to fix the code first
