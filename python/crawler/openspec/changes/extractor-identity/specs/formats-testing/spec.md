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
