# Tasks

## 1. The area `text`

- [x] 1.1 Subpackage `modama_formats_common/text/` with the eight formats, registered in `PARTS`; dependencies pinned in `pyproject.toml`. Verify: spec scenario "Text files of each kind" (`test_extract.py`), the plugin's fixture and coverage tests.
- [x] 1.2 The head, encoding and lines (`head.py`). Verify: the scenarios of "The encoding as detected" and "The line count up to a bound", bytes read counted with `/proc/self/io`.
- [x] 1.3 Markdown, reStructuredText, HTML, LaTeX and BibTeX (`markup.py`). Verify: one test per scenario of their requirements, `TZ=Europe/Berlin` and `TZ=UTC` for the front matter's time.
- [x] 1.4 Fixtures: generated (encodings, a log over the bound, a README, Markdown, BibTeX, HTML and LaTeX written by docutils), docutils' `tools.rst` (public domain), reproducers (binary and empty `.txt`); provenance in `fixtures.toml`; expected results reviewed. Verify: `pytest src` in `python/modama-formats-common`.
- [x] 1.5 README rows; the open points in `BACKLOG.md`. Verify: by reading.
- [x] 1.6 The CLI tests that used a text file as a file no format claims (crawler `test_cli.py`, `test_runs.py`; `modama-formats-em` `k2is/tests/test_extract.py`, now with `--select em` as its spec scenario says): with the common collection installed, `common/text` claims it. Verify: the crawler suite, the em suite.

## 2. Checks and review

- [x] 2.1 Crawler suite and the package's suite in a venv of their own; CI's ruff from the repo root. Verify: the commands' output in the hand-over.
- [ ] 2.2 Independent review started by main; findings verified and applied. Verify: the findings and the fixes in the hand-over.
