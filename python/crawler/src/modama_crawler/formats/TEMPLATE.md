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
    expected/        # recorded recognition results, one JSON per fixture, recorded on first run
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
    display_name = "Example Pair"  # in dc:subject; default: the type's <comment>
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

### A file that is not of its name's type

A glob decides a type without reading the file, so a text file named like
your format's files gets your type. Your format can check the file's first
bytes and say it is not of that type (change `recognition-checks-content`):

```python
class Workspace(Format):
    type = "application/x.example-workspace"  # *.exw in the XML, a name rule only
    priority = 61  # above the formats that are to claim its files' new types
    reacts_to = frozenset({type})

    def recognize(self, d: Directory):
        for e in d.of_type(self.type):
            # The signature only, as a content rule would test it; never parse to decide
            if d.read(e, 4) != b"EXW1":
                # The file gets the type it has without its name rule, for the
                # formats after this one and as a single file; the reason goes
                # into its dataset's basis
                d.not_of_type(e, "no EXW1 header")
                continue
            yield Dataset(anchor=e.rel, basis="EXW1 header")
```

- Only a type that one name rule gave is dropped. A file typed by its content
  keeps its type, and the crawl warns: the content rule is too weak.
- Decide what is broken by the files around it before you check: K2IS groups
  a `.gtg` with its 8 sector files whatever the `.gtg` holds (a broken
  capture, reported at extraction), and checks only a `.gtg` without them.
- The core finds the new type with a read that does not count against your
  budget. A read error there keeps the file's type and warns at it
  (`d.cannot_read`), and the directory is recognised again next crawl; your
  call goes on. Where one file's read error must not decide the others'
  outcome, catch `OSError` around your own `d.read` of it and call
  `d.cannot_read(e, error)` too (`modama_formats_em.dm.header`). An exception
  out of `recognize` discards all of your datasets of the directory.
- A file of your type that is odd but kept (a variant nobody has seen yet)
  can be flagged for a person with `d.note(e, "file of interest: …")`: the
  note goes into its dataset's basis, its type stays.
- Drop only types of files you react to: a drop of a file a format that ran
  earlier claimed is undone, with a warning.
- Order: a format that runs before yours does not see the new type. Give
  yours a higher priority than the formats that are to claim the new types.
  The crawl warns when a format that ran earlier reacts to a dropped file's
  new type; it cannot tell for formats that react to `DIRECTORY`.
- A changed priority needs a new recognition `version`: priorities are not
  part of the rule set's fingerprint, and a directory taken over from the
  last crawl keeps the outcome of the old order, types included.

## Extracting metadata

A format may also read metadata from its datasets' files, after recognition:

```python
from modama_crawler.formats import Extracted


class Pair(Format):
    ...
    # Raise it when the output changes: the datasets are extracted again
    extractor_version = "1"

    def extract(self, dataset, root):
        header = root + dataset.anchor  # a member's path on disk: root + member
        ...
        return Extracted(
            # "key value" phrases, the start of dc:description
            summary=["scan 256 x 256", "exposure 1 ms"],
            subjects=["4D-STEM"],  # short terms for dc:subject
            values={"scan": [256, 256], "exposure_s": 0.001},  # stored, not rendered
        )
```

`extract` runs in a worker process with a time limit, without database
access; plain JSON values only. It may open the members itself, unbuffered
(`open(path, "rb", buffering=0)`), or with a 64 KiB buffer and readahead off
for a library that reads in tiny pieces (see the README's pitfalls). If it raises,
crashes or runs over the limit, the dataset keeps a basic description and the
crawl reports a warning; the failure is kept until the files or the
`extractor_version` change. Return `None` if there is nothing to extract.

## Fixtures

Every file-specific rule you write needs at least one *representative*
fixture: a realistic file as found in the wild, or one written at test time
by the software that writes the format in practice. Reproducers for invalid or
incomplete files are the only exception from realism. A wild file too large or
not to be published whole may be cut to the bytes your rules and extractor read,
with the cut in `validity` and the tool that cut it beside the manifest
(`modama-formats-em`'s K2IS `capture52`). Manifest entry:

```toml
[pair]
purpose = "representative"        # or "reproducer"
validity = "vendor-written"       # or "validated-by: <tool>", "second-reader: <library>", "parser-only", "invalid-by-design: <why>"
licence = "CC0"
source = "where it came from, or what generated it"
generator = "package.tests.generate:pair"   # optional: writes the fixture into the given directory
```

Run `pytest <name>/tests` once: a fixture without a recorded result is recorded
and its test fails asking for a review; review `expected/*.json`, commit. From
then on `pytest` compares against them, checks the manifest both ways, and
fails if one of your globs, magic rules or formats never fires on a
representative fixture. After a rule change, `pytest --regen-expected
<name>/tests` rewrites the results and fails naming what changed, so that the
diff gets reviewed before it is committed. Your tests run with your definitions
and the core's only, whatever else is installed.

Try a directory by hand: `modama-crawler records --verbose PATH`.
