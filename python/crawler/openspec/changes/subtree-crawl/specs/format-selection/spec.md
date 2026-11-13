# Spec Delta

## ADDED Requirements

### Requirement: The configuration file comes from one setting
`modama-crawler` SHALL read its configuration file from `--config` when it is given, and otherwise from the path in `MODAMA_CRAWLER_CONFIG` when that is set and not empty, for every command that takes a configuration; without either, it SHALL use the defaults (everything installed enabled, nothing excluded).

#### Scenario: The setting names the file
- **WHEN** `MODAMA_CRAWLER_CONFIG` names a file that excludes `scratch/`, and `modama-crawler crawl` is run without `--config`
- **THEN** nothing under `scratch/` is crawled, and the run records that file as its configuration

#### Scenario: The command line wins
- **WHEN** `MODAMA_CRAWLER_CONFIG` names one file and `modama-crawler --config other.toml crawl` is run
- **THEN** the crawl uses `other.toml`
