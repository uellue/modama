# Spec Delta

## ADDED Requirements

### Requirement: The same data gives the same result or a failure
A crawl of the same data with the same rules SHALL give the same result, or fail; how long a step took (the load, the number of threads) SHALL NOT change what is recognised.

#### Scenario: Every format call slow
- **WHEN** a tree is crawled once with every format call counted as slow and once without
- **THEN** both results are identical, with the same datasets and warnings

### Requirement: The result does not depend on the number of threads
The crawl SHALL produce the same recognition result whatever number of threads it walks with: the same datasets with the same members, parts and parents, the same warnings and skipped entries, in the same order, and the same directories taken over from the last crawl.

#### Scenario: One thread against many on the fixture trees
- **WHEN** every fixture tree of every installed collection is crawled once with one thread and once with 16 threads
- **THEN** both results are identical

#### Scenario: Many threads with the last crawl's state
- **WHEN** a tree is crawled with 16 threads, a file three levels down is changed, and the tree is crawled again with 16 threads
- **THEN** the second result equals that of the same two crawls with one thread, and only the directories above the changed file are recognised again

#### Scenario: A collapsed directory with many threads
- **WHEN** a tree with a collapsed directory that contains subdirectories with many files is crawled with 16 threads
- **THEN** nothing below the collapsed directory is listed, classified or opened

### Requirement: The number of threads is a setting
The crawl SHALL walk with as many threads as `MODAMA_CRAWLER_WALK_THREADS` gives, 32 if it is not set; with 1 it SHALL do one thing at a time.

#### Scenario: A limit on reads in flight
- **WHEN** `MODAMA_CRAWLER_WALK_THREADS` is 4 and a tree of 50 files without a decisive name is crawled
- **THEN** at no time are more than 4 of them being read

#### Scenario: Not a number
- **WHEN** `MODAMA_CRAWLER_WALK_THREADS` is not a positive integer
- **THEN** the command fails with exit status 2 and an error naming the setting
