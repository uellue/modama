# AI Coding Agent Instructions - Modama OAI-PMH Crawler

This document helps AI coding agents quickly understand and be productive in the modama crawler codebase.

## Quick Start

### Environment Setup (CRITICAL)

**Always use the correct Python environment:**
- This project requires Python 3.14+ as specified in `pyproject.toml`
- VS Code is configured to use Conda for environment management
- Never run tests, installations, or any commands with system Python or base conda

**To determine and verify your environment:**

1. **Check VS Code's Python interpreter setting:**
   - Open Command Palette (Ctrl+Shift+P) → "Python: Select Interpreter"
   - Look for a path like `/home/weber/miniforge3/envs/*/bin/python`
   - This tells you which conda environment is configured

2. **Verify the environment before running commands:**
   ```bash
   # Check current Python path (VS Code should show this in status bar)
   which python
   
   # If not in the correct environment, activate it:
   conda activate crawler314  # or whatever your environment is named
   
   # Verify Python version (should be 3.14.x):
   python --version
   ```

3. **When in doubt, use your VS Code terminal** - The integrated terminal should already have the correct environment active

4. **Explicitly prefix commands if uncertainty persists:**
   ```bash
   # Replace <ENV_PATH> with the path shown by `which python`:
   /home/weber/miniforge3/envs/crawler314/bin/python -m pip install ...
   /home/weber/miniforge3/envs/crawler314/bin/pytest tests/
   ```

**⚠️ Common mistake to avoid:**
Running `pip install pytest` or `python pytest tests/` in the wrong environment (e.g., base conda) will fail because dependencies like `psycopg`, `flask`, and `pytest-postgresql` are only installed in the project's specific conda environment.

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
