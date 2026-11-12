# Spec Delta

## ADDED Requirements

### Requirement: A byte budget bounds every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading; exceeding it SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl.

#### Scenario: A format reads past its budget
- **WHEN** a format reads more bytes on a directory than its budget allows
- **THEN** its result is discarded, the directory is recognised by the remaining formats, and a warning names the format and the read

### Requirement: A slow format call keeps its result
A format call that takes longer than a set time SHALL keep its result and SHALL be logged with the format, the directory and the time it took; the log line SHALL NOT be one of the result's warnings, since the time depends on the load and the result must not. Stopping a call that hangs is deferred to worker subprocesses (architecture G).

#### Scenario: A slow format's result is kept
- **WHEN** a format takes longer than the set time on a directory
- **THEN** its result is kept, the result carries no warning about it, and the log names the format, the directory and the time it took

## REMOVED Requirements

### Requirement: Budgets bound every format call
**Reason**: Its time limit was checked after the call returned, so it never stopped a hang; it only discarded finished results, and under many threads that made the result depend on the load (review of `parallel-walk`, finding 2).
**Migration**: The byte budget stays as "A byte budget bounds every format call"; slow calls follow "A slow format call keeps its result".
