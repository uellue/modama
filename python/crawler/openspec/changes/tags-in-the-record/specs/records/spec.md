## ADDED Requirements

### Requirement: The file's tags go into a second description
A record whose dataset's extracted values hold `original_metadata` (a flat mapping of names to values, the entries the format kept from the file) SHALL carry, after the first `dc:description` (the summary), a second `dc:description` with one line per entry, `name: value`, sorted by name (design D1). Entries whose value is empty (`""` or `[]`) SHALL be left out; a record without other entries SHALL carry no second description (decision 234).

#### Scenario: A dataset with tags gets a second description
- **WHEN** a dataset's extracted values hold `original_metadata` with `Microscope Info.Voltage` 300000.0, `DataBar.Device Name` `K2-IS-0001` and a tag no format knows, `Foo Vendor.New Setting` 7
- **THEN** its record has two `dc:description`: the summary first, then the lines `DataBar.Device Name: K2-IS-0001`, `Foo Vendor.New Setting: 7` and `Microscope Info.Voltage: 300000.0`

#### Scenario: A dataset without tags gets none
- **WHEN** a dataset has no extraction, or its values hold no `original_metadata`, or only entries with empty values
- **THEN** its record has one `dc:description`, the summary

#### Scenario: Empty values are left out
- **WHEN** a dataset's `original_metadata` holds `Session Info.Operator` `[]`, `QuickSaved.fields.minitext` `""` and `Session Info.Specimen` `Au`
- **THEN** the second description is the line `Session Info.Specimen: Au` alone

#### Scenario: Sorted by name, the same for a stored extraction
- **WHEN** a dataset's `original_metadata` holds its entries in another order than by name, and the dataset is stored and its extraction reused by the next crawl
- **THEN** the lines are sorted by name, the record built from the stored extraction is the same, and the record keeps its datestamp

#### Scenario: The served record and the records command show the tags
- **WHEN** the K2IS fixture Capture52 is crawled and served, or given to `modama-crawler records --verbose`
- **THEN** the record has two `dc:description`, the second starting with the line `Acquisition.Device.Active Size (pixels): [1920, 1792]`

### Requirement: Tag values as stored
In the tag description, a string value SHALL appear as it is stored, any other value as its JSON text, not rounded and without units added, with numbers as the database gives them back (design D2). A value whose text is longer than 4,096 characters (the storage's limit for a string) SHALL be cut to that length and end in `…` (design D3).

#### Scenario: Values as stored
- **WHEN** an entry's value is the list `[1920, 1792]`, the number -2.4043772802208405, or the string `inf`
- **THEN** its line shows `[1920, 1792]`, `-2.4043772802208405` and `inf`

#### Scenario: Numbers as the database gives them back
- **WHEN** an entry's value is the number 1.316679648365784e+17 or -0.0
- **THEN** its line shows `131667964836578400` or `0.0`, whether the extraction ran in this crawl or was stored by the last one

#### Scenario: A very long value is cut
- **WHEN** an entry's value is a list whose JSON text is longer than 4,096 characters
- **THEN** its line shows the first 4,096 characters of that text followed by `…`
