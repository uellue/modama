-- The schema the crawler made before migrations: the eight statements of
-- ensure_tables in `git show e35e4b4:python/crawler/src/modama_crawler/store.py`
-- (identical at 3251cad, which made staging's database), as plain SQL.
-- Taken from the old code, not from 0001_baseline, so that it stays the old
-- schema whatever happens to 0001 (database-schema spec, "A database made
-- before migrations"; design D9 of the change schema-migrations). Never edit.

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id SERIAL PRIMARY KEY,
    anchor TEXT NOT NULL UNIQUE,
    type TEXT NOT NULL,
    format TEXT NOT NULL,
    version TEXT NOT NULL,
    basis TEXT NOT NULL,
    warnings JSONB NOT NULL,
    parent TEXT,
    collapsed BOOLEAN NOT NULL,
    mtime DOUBLE PRECISION NOT NULL,
    uid INTEGER NOT NULL,
    parts JSONB NOT NULL,
    size BIGINT NOT NULL,
    stamp TEXT NOT NULL,
    directory TEXT NOT NULL,
    extractor TEXT,
    extractor_version TEXT,
    extracted JSONB,
    extract_error TEXT,
    extract_seconds DOUBLE PRECISION,
    extract_retry BOOLEAN
);
CREATE INDEX IF NOT EXISTS datasets_directory ON datasets (directory);
CREATE TABLE IF NOT EXISTS members (
    dataset_id INTEGER REFERENCES datasets(dataset_id) ON DELETE CASCADE,
    path TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS members_dataset ON members (dataset_id);
CREATE TABLE IF NOT EXISTS directories (
    path TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    pre_warnings JSONB NOT NULL,
    post_warnings JSONB NOT NULL,
    retry BOOLEAN NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    record_id SERIAL PRIMARY KEY,
    identifier TEXT NOT NULL UNIQUE,
    datestamp TIMESTAMPTZ NOT NULL,
    metadata JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS records_datestamp ON records (datestamp, record_id);
CREATE TABLE IF NOT EXISTS crawl_runs (
    run_id SERIAL PRIMARY KEY,
    root TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,
    outcome TEXT CHECK (outcome IN ('finished', 'failed')),
    directories INTEGER NOT NULL DEFAULT 0,
    files INTEGER NOT NULL DEFAULT 0,
    datasets INTEGER,
    warnings INTEGER,
    records_changed INTEGER,
    extractions_run INTEGER,
    extractions_reused INTEGER,
    extractions_failed INTEGER,
    directories_unchanged INTEGER,
    error TEXT,
    rules TEXT
);
