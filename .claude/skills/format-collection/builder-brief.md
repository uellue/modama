# Brief for a builder of one format area

Fill in the `<…>` before handing it to a coding agent; delete what does not apply. Made
from the brief of the night of 2026-11-12 (five areas of `modama-formats-common`).

## The task

The person's request, verbatim: <quote>. The answers from looking at the sample files
with them (SKILL.md, step 1): <answers, or a link>. Your area: `<area>` in the package
`python/modama-formats-<domain>` (import `modama_formats_<domain>`, collection
`<domain>`), as a subpackage `src/modama_formats_<domain>/<area>/`.

## Read first

- `python/crawler/src/modama_crawler/formats/TEMPLATE.md`, all of it: the core
  requirements, the steps, "Testing a format" and the checklist at its end. Follow
  every point.
- `/AGENTS.md` and `python/crawler/AGENTS.md`: the standing rules (edit files with the
  Edit and Write tools, a hook refuses shell edits; path-limited commits checked with
  `git diff --cached --stat`, never `git commit -a`; no push).
- `python/modama-formats-em/README.md`, "Values and units".
- The core's MIME database (`python/crawler/src/modama_crawler/formats/core/`,
  `freedesktop.org.xml`, `er-c.xml`): many types are there already, so the work is
  often extraction, plus a subtype where the core's type is too general.

## How

- An OpenSpec change of your own, `<change name>`, in `python/crawler/openspec/changes/`:
  proposal with the assumptions and leans, delta specs `formats/<area>/…`, tasks.
  Scenarios first, then tests, then code.
- Readers: the established library for each format, pinned exactly with a comment, its
  current release looked up on PyPI, wheels for Python 3.14 checked; if it has none and
  does not build, say so and take the next established one. Name every new dependency
  in the hand-over. Where a reader fails on real files, work around it here with a test
  from the case, and add its bug to `python/crawler/BACKLOG.md`, "Sync with upstream",
  as *worked around here*.
- Fixtures: small, public test data with licence and source in `fixtures.toml` and a
  `LICENSE.fixtures` (the reader's own test files are often the best source), or
  generated at test time by the program that writes the format. Never a file from
  staging or the data tree without its owner's agreement.
- Shared files: other builders add their area too. Keep your edits of the package's
  `__init__.py` (one import, one `PARTS` entry), its README table and `pyproject.toml`
  minimal, so that merges stay simple. Merge `crawler` into your branch at the start
  and before the hand-over.
- Resources: your worktree branched from `crawler`; your own venv
  (`uv venv --python 3.14 /var/tmp/<area>/venv`, then
  `uv pip install --python /var/tmp/<area>/venv/bin/python -e "python/crawler[test]" -e "python/modama-formats-<domain>[test]"`
  and the other format packages); `--basetemp` and `TMPDIR` under `/var/tmp/<area>/`
  (`/tmp` is a RAM disk shared by every coding agent); remove them at the end. No image
  builds, no search stack, no staging, no secrets, unless the person says so.
- When the code is ready, send the main session the range to review; apply the review's
  findings it sends back; then hand over.

## Checks

`pytest src` in the package, also with `TZ=Europe/Berlin`; the crawler's suite;
`uvx ruff format --check --diff` and `uvx ruff check` from the repository root (known
errors: `python/crawler/BACKLOG.md`).

## Hand-over

As SKILL.md, step 6: for people first (formats, an example summary line and a few
`original_metadata` lines each, the skip list, new dependencies with versions,
questions numbered Q1, Q2 with leans); then commits and commands with output.
