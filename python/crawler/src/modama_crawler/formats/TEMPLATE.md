# Writing a format collection

A collection is a directory with this layout; copy it and rename:

```
<name>/
  __init__.py        # COLLECTION = Collection("<name>", [Format(), ...], mime_files=(HERE / "<name>.xml",))
  <name>.xml         # XDG shared-mime-info rules: globs, magic, sub-class-of (optional)
  tests/
    __init__.py
    test_fixtures.py # one line: from modama_crawler.testing import test_coverage, test_fixture, test_manifest  # noqa: F401
    fixtures.toml    # provenance of every fixture: purpose, validity, licence, source, optional generator
    fixtures/<name>/ # fixture directories holding only wild files (or generated at test time)
    expected/        # recorded recognition results, one JSON per fixture, written with --regen-expected
    generate.py      # generators for fixtures that a real producer writes at test time (optional)
```

Register it in `pyproject.toml` under `[project.entry-points."modama.formats"]` as
`<name> = "<package>:COLLECTION"`; the collection's name must be unique.

## Rules first, Python second

Single-file types go into the XML, as valid shared-mime-info rules. Name a
type after one already used in the wild for the format (check the Debian MIME
support list and reader libraries such as LiberTEM or HyperSpy); if none
exists, invent an unofficial `application/x.<name>` type. Never leave a format
on a misleading generic type such as `text/plain` for a text header with
binary frames. Where a vendored upstream definition is wrong for us, curate it
in `core/er-c.xml` by forcing a content check (a tie), not by editing
`freedesktop.org.xml`. Python is
for what the XML can't say: several files that belong together, a directory
that is one dataset. A format is a class:

```python
from modama_crawler.formats import DIRECTORY, Collection, Dataset, Directory, Format


class Pair(Format):
    type = "application/x.example"  # the MIME string of the datasets it produces
    priority = 60  # 0..100, the XDG scale; higher runs first
    reacts_to = frozenset(
        {"application/x.example-header"}
    )  # MIME types present, or {DIRECTORY}
    collection = False  # True if it adopts child datasets (nesting)

    def recognize(self, d: Directory):
        # d.phase is "pre" (names and sizes only; return a collapsed dataset to stop the descent)
        # or "post" (entries with MIME types, d.children = datasets of subdirectories)
        for header in d.of_type("application/x.example-header"):
            data = d.read(header, 64 * 1024)  # the only I/O, counted against the budget
            raw = d.entry("the-name-the-header-says")  # a sibling, or None
            if raw is None:
                d.warn(
                    header.rel, "raw file missing"
                )  # reported, the header stays a single file
                continue
            yield Dataset(
                anchor=header.rel,
                members=(header.rel, raw.rel),
                basis="header names the raw file",
            )
```

Rules: claim only entries of `d` and whole child datasets (`parts=`); never
open files yourself; keep `recognize` fast, it has a time limit per directory.

## Fixtures

Every file-specific rule you write needs at least one *representative*
fixture: a realistic file as found in the wild, or one written at test time
by the software that writes the format in practice. Reproducers for invalid or
incomplete files are the only exception from realism. Manifest entry:

```toml
[pair]
purpose = "representative"        # or "reproducer"
validity = "vendor-written"       # or "validated-by: <tool>", "second-reader: <library>", "parser-only", "invalid-by-design: <why>"
licence = "CC0"
source = "where it came from, or what generated it"
generator = "package.tests.generate:pair"   # optional: writes the fixture into the given directory
```

Run `pytest <name>/tests --regen-expected` once to record the results, review
`expected/*.json`, commit. From then on `pytest` compares against them, checks
the manifest both ways, and fails if one of your rules never fires.

Try a directory by hand: `modama-crawler records --verbose PATH`.
