# AI Coding Agent Instructions - Modama OAI-PMH Crawler

This document helps AI coding agents quickly understand and be productive in the modama crawler codebase.

## Quick Start

### Build/Test Commands

```bash
# Install dependencies (from within python/crawler directory)
pip install -e ".[test]"

# Run all tests
pytest

# Run specific test file
pytest tests/test_server.py
pytest tests/test_database.py
pytest tests/test_recognition.py

# Run with verbose output
pytest -v

# Run tests matching pattern
pytest -k "test_name_pattern"
```

### Environment Setup

1. Copy `.env.example` to `.env`
2. Fill in PostgreSQL connection details (see `.env.example`)
3. The crawler uses the `crawler314` conda environment with Python 3.14+

## Architecture Overview

The modama crawler is an OAI-PMH server implementation with PostgreSQL backend:

```
src/modama_crawler/
├── server.py           # Flask app factory + OAI-PMH verb implementations
├── database.py         # PostgreSQL connection pooling + crawling logic  
├── mime_sql.py         # SQL-based MIME type detection and dataset creation
├── recognition.py      # FileHandler pattern for different file types
└── repository.py       # Identifier/path conversion utilities

tests/
├── conftest.py         # Shared pytest fixtures (CRITICAL)
├── test_server.py      # Flask server endpoint tests
└── ...                 # Other test files
```

## AI Coding Agent Tools Guide

### ✅ **Preferred Tools (Safe & IDE-Integrated)**

**File Access & Analysis:**
- `read_file` - Read file contents with line ranges for large files
- `grep_search` - Fast text/regex searches across workspace
- `file_search` - Glob pattern file lookups
- `list_dir` - List directory contents
- `get_errors` - Get compile/lint errors in files

**File Modification:**
- `replace_string_in_file` - Safe string replacement with context matching
- `insert_edit_into_file` - Insert code at specific locations
- `create_file` / `create_directory` - New file creation

**Search & Exploration:**
- `vscode_listCodeUsages` - Find all references/definitions of symbols
- `vscode_renameSymbol` - Semantic-aware renaming across workspace
- `copilot_getNotebookSummary` - Get Jupyter notebook cell summaries

**Terminal Execution (Selective Use):**
- `run_in_terminal` - Run shell commands (use sync mode for one-shot tasks)
- `run_notebook_cell` / `configure_notebook` - Execute Jupyter cells
- `get_task_output` / `get_terminal_output` - Get command results

**Testing:**
- `testFailure` - Get recent test failure details
- `run_in_terminal` with pytest commands for test runs (OK for running tests)

**Memory & Configuration:**
- `memory` - Manage persistent notes in `/memories/`
- `session_store_sql` - Query past session history

### ⚠️ **Use With Caution**

- Shell commands that modify files (sed, awk, sed scripts)
- Any workflow that involves writing a Python script to modify things
- Complex multi-step shell pipelines for file editing

### ❌ **Forbidden Approaches**

- Writing Python/Ruby/Shell scripts whose sole purpose is to modify project files
- Using `echo "..." >> file.txt` or similar for bulk modifications
- Creating temporary scripts and then executing them for file manipulation
- Any approach that bypasses IDE-integrated tools for file operations

---

## Key Patterns & Conventions

### Database Access Pattern

**Always use connection pooling with `psycopg`:**

```python
from psycopg_pool import ConnectionPool
from modama_crawler.server import PostgresConfig

pool = ConnectionPool(
    conninfo=PostgresConfig.from_env().connection_string(),
    min_size=1,
    max_size=2,
)

with pool.connection() as conn:
    cur = conn.cursor(row_factory=dict_row)
    # ... database operations
```

**Never:**
- Use standalone `psycopg.connect()` without pooling
- Access environment variables directly (use `PostgresConfig.from_env()`)
- Forget `row_factory=dict_row` for cursor instantiations

### Flask Application Factory Pattern

```python
from modama_crawler.server import create_app

app = create_app(
    pool=connection_pool,
    root=pathlib.Path("/path/to/data"),
    config={"TESTING": True}  # Optional
)
```

### Testing Fixtures (Critical)

**`conftest.py` provides these essential fixtures:**

| Fixture | Purpose |
|---------|---------|
| `test_database` | Full test database with schema and data |
| `pg_unit_test` | Empty isolated PostgreSQL connection |
| `flask_client` | Flask test client with monkeypatched DB connection |
| `running_http_server` | HTTP server fixture for integration tests |

**Test types:**
- **Unit tests** (no data): Use `pg_unit_test` directly
- **Integration tests** (with data): Use `test_database` + `test_files`
- **HTTP endpoint tests**: Use `flask_client`

### OAI-PMH Implementation

The server implements all 6 required verbs:
1. `Identify` - Repository information
2. `GetRecord` - Single record retrieval
3. `ListMetadataFormats` - Available formats
4. `ListIdentifiers` - Header-only list with pagination
5. `ListRecords` - Full records with pagination
6. `ListSets` - Available sets (currently empty)

**Key features:**
- Path-based continuation tokens (JSON-encoded in URL)
- Date filtering via `from`/`until` parameters
- Configurable batch size (`BATCH_SIZE` environment variable, default: 10)
- Supports selective harvesting

### FileHandler Pattern

Each file type has a handler subclassing `FileHandler`:

```python
class MyHandler(FileHandler):
    file_types = ("my/type", "other/type")
    
    def x_md5(self) -> str:
        return calculate_md5()
    
    def x_dc_title(self) -> list[str]:
        return [self.get_title()]
```

**MIME type resolution:** Database lookups first, then filesystem guessing via `modama_crawler.recognition.guess()`.

## Gotchas & Common Pitfalls

### 🔴 Critical Gotchas

1. **PostgreSQL-only** - No SQLite support anywhere
   - Always use `%s` placeholders (not `?`)
   
2. **Connection pooling required** - Production code always uses `ConnectionPool`
   - Tests also need explicit pool creation
   
3. **Test isolation is mandatory**
   - Never connect to production database
   - Use fixtures from `conftest.py`, not direct connections
   
4. **Environment variables**
   - Use `PostgresConfig.from_env()` instead of reading env vars directly
   - `.env` file is not committed (see `.env.example`)
   
5. **Path handling**
   - Database stores absolute paths
   - API responses use relative paths (relative to root)
   - `path_from_identifier()` and `sanitize()` handle conversion

6. **Python 3.14+** - Requires very recent Python version

### ✅ Best Practices

- Use `row_factory=dict_row` for all cursors
- Always wrap database operations in `with pool.connection() as conn:`
- Test with `pytest` before committing changes
- Check `POSTGRESQL_MIGRATION_SUMMARY.md` for SQL syntax differences from SQLite
- See `TEST_ISOLATION_NOTES.md` for testing patterns

## Key Files Reference

| File | Purpose |
|------|---------|
| `src/modama_crawler/server.py` | Flask app factory + OAI-PMH verb implementations |
| `src/modama_crawler/database.py` | Connection pooling, crawling, population |
| `src/modama_crawler/mime_sql.py` | SQL-based MIME detection and dataset creation |
| `src/modama_crawler/recognition.py` | FileHandler pattern implementation |
| `tests/conftest.py` | **Shared pytest fixtures - READ THIS FIRST** |

## Testing Strategy

1. **Unit tests** (fast, no external dependencies):
   ```python
   def test_something(pg_unit_test):
       # Test logic without database access
   ```

2. **Integration tests** (database with test data):
   ```python
   def test_with_data(test_database, test_files):
       # test_database has schema + data
       # test_files has the actual files on disk
   ```

3. **HTTP endpoint tests**:
   ```python
   def test_endpoint(flask_client):
       response = flask_client.get("/oai?verb=Identify")
   ```

## Additional Documentation

- `POSTGRESQL_MIGRATION_SUMMARY.md` - SQLite to PostgreSQL migration details
- `TEST_ISOLATION_NOTES.md` - Testing pattern history and improvements
