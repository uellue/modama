## ADDED Requirements

### Requirement: A slow extraction is flagged for review
A successful extraction that took more than 10 s SHALL leave its dataset with the warning `<format> extraction took <seconds> s; slow extraction`, stored with the dataset, so that `modama-chain review` lists it under the kind `slow extraction` (@weber 352). A failed extraction SHALL NOT be so flagged; it is warned as failed. The warning SHALL follow the stored extraction: a reused extraction keeps exactly one, whether its folder is taken over or recognised again.

#### Scenario: A slow extraction
- **WHEN** one extraction succeeds after more than the threshold, one returns at once and one runs over the time limit
- **THEN** the first dataset has the warning `t/stand extraction took <its seconds> s; slow extraction`, the one over the time limit has none, and the quick one has it only if its time, process start included, was over the threshold

#### Scenario: A reused slow extraction keeps its warning
- **WHEN** a slow extraction is stored, and the tree is crawled again unchanged, then again with a new file in its folder
- **THEN** both crawls reuse the extraction, and the stored dataset has the same one warning after each

### Requirement: The crawl reports its slowest extractions
The crawl's report SHALL name the 10 slowest extractions it ran, failed ones included, as path, format and seconds, slowest first, in the line after its first; a finished crawl SHALL store them with its run, and `modama-crawler runs` SHALL show them on the run's line (@weber 352).

#### Scenario: The slowest extractions
- **WHEN** a crawl extracts 12 datasets
- **THEN** the report's second line is `slowest extractions: ` followed by the 10 with the longest times, as `<path> <format> <seconds, one decimal> s`, slowest first

#### Scenario: The slowest extractions stay with the run
- **WHEN** a crawl extracts two datasets and `modama-crawler runs` is run
- **THEN** the run's line has `; slowest: ` followed by both, slowest first, with their stored times
