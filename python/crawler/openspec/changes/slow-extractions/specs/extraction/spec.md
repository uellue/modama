## ADDED Requirements

### Requirement: A slow extraction is flagged for review
A successful extraction that took more than 10 s, timed in its worker process from the extractor's call, SHALL leave its dataset with the warning `<format> extraction took <seconds> s; slow extraction`, stored with the dataset, so that `modama-chain review` lists it under the kind `slow extraction` (@weber 352). A failed extraction SHALL NOT be so flagged; it is warned as failed.

#### Scenario: A slow extraction
- **WHEN** every worker process takes longer than the threshold to start, and one extraction then succeeds after more than the threshold, one returns at once and one runs over the time limit
- **THEN** the first dataset has the warning `t/stand extraction took <its seconds> s; slow extraction`, its seconds without the worker's start, and the other two have none

### Requirement: A slow extraction's warning follows the stored extraction
A reused slow extraction SHALL keep exactly one such warning, whether its folder is taken over or recognised again (@weber 352).

#### Scenario: A reused slow extraction keeps its warning
- **WHEN** a slow extraction is stored, and the tree is crawled again unchanged, then again with a new file in its folder
- **THEN** both crawls reuse the extraction, and the stored dataset has the same one warning after each

### Requirement: The crawl reports its slowest extractions
The crawl's report SHALL name the 10 slowest extractions it ran as path, format and seconds, slowest first, a failed one marked `(failed)`, in the line after its first (@weber 352). The run SHALL NOT store them.

#### Scenario: The slowest extractions
- **WHEN** a crawl extracts 12 datasets, and one of them runs over the time limit
- **THEN** the report's second line is `slowest extractions: ` followed by the 10 with the longest times, as `<path> <format> <seconds, one decimal> s`, slowest first, the one over the time limit first and marked ` (failed)`
