# Spec Delta

## MODIFIED Requirements

### Requirement: Budgets bound every format call
Each format call on a directory SHALL have a byte budget for reads, enforced while reading; exceeding it SHALL discard that format's result for that directory with a warning naming the format, and SHALL NOT stop the crawl. A call that takes longer than a set time SHALL keep its result and SHALL be logged with the format, the directory and the time it took, not added to the result's warnings (the time depends on the load, the result must not); stopping a call that hangs is deferred to worker subprocesses (architecture G).

#### Scenario: A slow format's result is kept
- **WHEN** a format takes longer than the set time on a directory
- **THEN** its result is kept, the result carries no warning about it, and the log names the format, the directory and the time it took
