## ADDED Requirements

### Requirement: An extractor's warnings are flagged at its dataset
When a successful extraction's values hold `warnings`, a list of strings, the crawl SHALL warn each string at the dataset, set anew from the stored extraction at every crawl, as the slow-extraction warning is, so that a reused extraction keeps exactly one of each. Strings that end in a fixed marker are listed by `modama-chain review` by that marker.

#### Scenario: A warning from the extractor
- **WHEN** a dataset's extraction gives `values["warnings"]` `["common/docx read 1,572,864 bytes of XML to render its text; large document text"]`
- **THEN** the dataset carries that warning, and `modama-chain review` lists it under `large document text`

#### Scenario: A reused extraction
- **WHEN** the same dataset is crawled again with its extraction reused
- **THEN** it carries that warning once

#### Scenario: No warnings
- **WHEN** an extraction's values hold no `warnings`
- **THEN** the dataset's warnings are as before
