# Design

## Context

See `proposal.md` for motivation. The decisions this design implements are recorded in `design/architecture.md` (sections A, B, C, D, E, H and the decision log through 2026-10-16) and `design/testing.md`; this document says how they become code and does not re-argue them.

Current state: `mime.py` implements the shared-mime-info checking order and is kept; `server.py` reads a `records` table and is kept; `records.py` holds the identifier, browse-URL and Dublin Core mapping, kept and split; `database.py` holds a flat `os.walk` crawl and a one-dataset-per-file schema, replaced; `recognition.py` holds a request-time `FileHandler` registry, removed. Constraints that shape the approach: the pipeline must run without PostgreSQL (`records` command, fixtures), formats must be writable by agents from one template, and the format interface must be plain data so that formats can later run in worker processes.

## Goals / Non-Goals

**Goals:**
- One code path from a tree to a recognition result, used by the crawl, the `records` command and the fixture plugin.
- A format template that an agent can copy: one directory with XML, an optional Python module, fixtures, a manifest.
- Prove post-order recognition, pre-order collapse, the XDG plus Python split, and the oracle on four real shapes.

**Non-Goals:**
- Performance beyond "a full crawl of the visible tree finishes": no parallel walk, no checkpointing, no worker processes.
- Separate distributions for collections; the entry-point group exists, the collections live in the package.
- Any format beyond core, collapse, zarr and empad.

## Decisions

**Module layout.** `modama_crawler/walk.py` (post-order walk, pre-order check, budgets), `formats/__init__.py` (the `Format`, `Directory`, `Entry`, `Dataset`, `Result` dataclasses and the runner that applies priorities, claims and warnings), `selection.py` (entry points, `select`/`ignore`, per-path ignores, crawl excludes), `mimedb.py` (build the database directory from enabled collections and point pyxdg at it; `mime.py` keeps classification), `records.py` (identifier, browse URL, Dublin Core mapping from a `Dataset`) and `render.py` (`oai_dc` XML, shared with `server.py`), `store.py` (schema and upsert of results into PostgreSQL, replacing `database.py`), `cli.py` (`crawl`, `serve`, `records`), `testing.py` (the pytest plugin, registered as a `pytest11` entry point). Alternative considered: keeping everything in `database.py` and `recognition.py`; rejected because the oracle requirement needs the pipeline free of the database.

**The format interface.** A class with class attributes `type`, `priority`, `reacts_to` (a set of MIME strings, or `{"directory"}`), `collection` and a method `recognize(self, directory) -> Iterable[Dataset]`. `Directory` carries `path`, `entries` (list of `Entry(name, path, size, mtime, ctime, kind, mime)`; `mime` is `None` in the pre-order call), `children` (list of `Dataset`, empty pre-order), and `read(path, n)`, the only I/O, which enforces the byte budget. `Dataset` is a frozen dataclass; a format sets `anchor`, `members`, `basis`, `warnings`, `parts` (child datasets it adopts), `collapsed`; the runner fills `type`, `format`, `version`, `parent`. The same class answers both calls; it inspects `directory.entries[0].mime is None` or a `phase` attribute to know which. Alternative: two hook functions per format (`collapse`, `recognize`); rejected because collapse formats would implement one and everything else the other, and the single method keeps the template uniform.

**The runner.** For a directory: pre-order, call every enabled format whose `reacts_to` contains `"directory"`, in priority order; the first collapsed dataset wins and the walk does not descend. Post-order, classify entries with `mime.py`, then call every format whose `reacts_to` intersects the present types or contains `"directory"`, in descending priority then id; claimed entries and adopted children are removed from what later formats see; a claim outside the directory or on something already claimed is dropped with a warning. Remaining regular files become single-file datasets of their type. Budgets: `signal.alarm`-free time limit by checking elapsed time after each format and a byte counter in `read`; a format that exceeds either is skipped for the directory with a warning. Alternative: enforcing the time limit by killing a worker; deferred with G, the interface allows it later.

**Tie resolution in classification.** `mime.py` gains the `sub-class-of` walk for ties: the candidates' common ancestor replaces the fallback, with the candidates recorded as a warning on the entry. pyxdg exposes `inherits_from()` for this.

**The MIME database build.** At startup, the enabled collections' XML files are copied into a temporary `mime/packages/` directory, `update-mime-database` runs on it, and `XDG_DATA_HOME` and `XDG_DATA_DIRS` are set to that directory before pyxdg loads. The core collection vendors `freedesktop.org.xml` with its GPL-2.0-or-later notice as a separate file. Alternative: reading the XML with our own parser; rejected because pyxdg's `globs2`/`magic` readers already exist and the spec checking order is implemented against them.

**Selection.** Ids are `collection/format`. `select` and `ignore` resolve by specificity then ignore-wins, implemented as ruff documents it. Per-path ignores and crawl excludes use gitignore-style patterns through the `pathspec` library if available, otherwise `fnmatch` on normalised paths; the decision on the dependency is left to implementation (see Open Questions). Entry points: group `modama.formats`, each entry point names a module whose `COLLECTION` object lists the XML files and the format classes; the four in-package collections are registered in the crawler's own `pyproject.toml`.

**Storage.** Tables: `files(path_id, path, parent_id, size, mtime, ctime, uid, mime)`, `datasets(dataset_id, type, anchor_id → files, format, version, basis, warnings jsonb, parent_id → datasets, collapsed)`, `files_in_datasets(dataset_id, path_id)`, `records(dataset_id, identifier, datestamp, metadata jsonb)` as today. The crawl writes the recognition result of the whole tree after the walk; records are upserted with the datestamp rule from today's `publish_records`. No migrations: the development database is recreated. Members as a template is left to the series change.

**The `records` command.** Runs the walk on the path with the selection from the configuration overridden by `--select`/`--ignore`, builds records with the datestamp set to the newest member mtime (no store), filters `--from`/`--until`, renders one `ListRecords` document with `render.py`, writes diagnostics to stderr via `logging` with `--verbose` lowering the level to per-dataset detail.

**The fixture plugin.** Discovers `tests/fixtures/*` of the collection under test (the collection is identified by a `conftest.py` one-liner or by the package containing the test file), reads `tests/fixtures.toml` with `tomllib`, runs the pipeline on each fixture directory with only that collection and core enabled, compares the result (as JSON with paths relative to the fixture) with `tests/expected/<name>.json`, honours `--regen-expected`, and checks manifest completeness, fixture-tree cleanliness and the coverage rule from the basis strings and the XML rules that fired. Generated fixtures: a fixture entry may name a generator function in the collection's tests that creates the directory in a temporary location at test time (venv via `python -m venv`, `.git` via `git init`, Zarr via zarr-python, EMPAD via the cheat generator); the manifest records the producer. Alternative: pytest-regressions as a dependency; rejected, the comparison is thirty lines and the binding by fixture name is the point.

**The collections.** `formats/core/` (core.xml with the vendored upstream file beside it, no Python), `formats/collapse/` (one `Collapse` base with a marker predicate per kind, pre-order only), `formats/zarr/` (pre-order on `zarr.json`, reads it within budget for the warning case), `formats/empad/` (XML magic rule and raw glob at weight 80 in `empad.xml`; the recognizer parses the header with `defusedxml` within budget, finds the raw sibling, builds the pair). The EMPAD cheat fixture: a real header with the scan reduced to 2×2 and a zero-filled raw of 4 × 130 × 128 × 4 bytes, generated at test time; validated once with LiberTEM outside the test suite and recorded as `second-reader: libertem` in the manifest.

## Risks / Trade-offs

- [A format that reads beyond its budget through its own means] → the reader is the only I/O the interface offers; a format that opens files itself is a review finding, and the worker boundary of G closes the hole later.
- [The time limit cannot interrupt a C extension in-process] → accepted for this change; the interface is worker-ready, and the crawl continues after the directory finishes.
- [Writing the whole result after the walk holds it in memory] → fine for the visible tree; streaming per subtree is possible with post-order if memory becomes the limit.
- [`update-mime-database` is an external binary] → already a devcontainer dependency through shared-mime-info; its absence fails startup with a clear message.
- [The core's own XML rules need representative fixtures (coverage rule)] → the core defines no rules of its own in this change; it vendors upstream, which is exempt.
- [Recorded expected results churn when the format version changes] → the version is excluded from the comparison; the basis is compared.

## Migration Plan

Development database: drop and recreate (`AGENTS.md` has the command). No production deployment exists. Rollback is the previous commit.

## Open Questions

- Whether to add `pathspec` for gitignore-style patterns or implement the subset we need; decided at implementation time, either satisfies the spec.
- The exact field names in the result JSON recorded for fixtures; settled by the first recorded fixture and kept from then on.
