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

To see what a format makes of real files while you write it: `modama-chain browse` in the search stack (`python/search-chain/README.md`, "browse"). Pick a file, and the page shows its dataset, the record and how the warehouse and Matchmaker will show it, computed by the checkout's code; an edit to the format shows on the next reload, without a build or a crawl. "Save for Claude" keeps a view, with a message, for a chat about it.

What to keep (@weber, decisions 129 and 230): what the file says, without editorializing. With a reader that maps metadata to standard names (RosettaSciIO), take its original metadata first, complete but for GUI settings and large arrays, and the mapped metadata as a second, labelled section; where they disagree, the original wins. Interpreting metadata across vendors is out of scope: the user makes their own sense of what the file says (`python/modama-formats-em/README.md`, "Values and units").

Keep every entry the file has, minus a skip list, never a list of wanted entries (@weber, 2026-11-12, for all formats: "we may encounter new and different tags in different files. So we don't keep a positive list, but a negative 'skip these' list"). A header with key/value lines keeps all its keys; a tag tree keeps all its tags; the skip list (GUI settings, placeholders, and content not suitable for text display: too large, such as long arrays and very long strings, or binary, such as raw bytes, unread arrays and text full of control characters) is one named list per format, documented in its spec with examples; the size and binary checks are the same for every format (`modama_crawler.formats.values.textual`). A summary line's few chosen entries are the only positive list. Test it with an entry nobody has seen before: it must arrive in the values.

A format may also read metadata from its datasets' files, after recognition:

```python
from modama_crawler.formats import Extracted


class Pair(Format):
    ...

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
for a library that reads in tiny pieces (see the README's pitfalls). It reads
the dataset's members only: a change to any other file would not bring it to
run again. If it raises, crashes or runs over the limit, the dataset keeps a
basic description and the crawl reports a warning; the next crawl tries again.
Return `None` if there is nothing to extract. There is no version to raise
when the output changes: a change to the installed code (yours, or a library
it uses) changes the crawl's extractor identity, and the next crawl extracts
every dataset again. The fixture tests record each fixture's extraction next
to its recognition result, so a change of output shows as a diff to review.

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

## Lessons from the EM formats

A checklist for every new format, from what `modama-formats-em` taught (where each comes from in brackets; the decision log is `design/architecture.md`).

- [ ] **The established reader**: read each format with its field's standard library (Pillow or tifffile, h5py, zarr, nbformat, the office libraries, pypdf, PyYAML …), a dependency of your collection, pinned as `modama-formats-em` pins RosettaSciIO and flagged in the hand-over; a parser of your own only where no established reader exists. Where the reader fails on real files, work around it here, with a test from the real case, and record its bug in `python/crawler/BACKLOG.md`, "Sync with upstream", as *worked around here*. (@weber 2026-11-12: "new dependencies are no issue … don't build unusual things just to save on dependencies"; "if an upstream reader struggles with real world files … we 'get it done' somehow and take note"; decision log; dm, merlin, blockfile use RosettaSciIO, and the Merlin header is read in Latin-1 by us)
- [ ] **What the file says, without editorializing**: no rounding, no unit guessed from a value's size or converted, no number from one entry joined with a unit from another; interpreting metadata across vendors is out of scope. (@weber 2026-11-11; decision log 2026-11-12, 230; `modama-formats-em` README, "Values and units")
- [ ] **`original_metadata`**: flat dotted names (`a.b[2].c`) to values as found, every entry the file has minus one skip list per format (GUI settings, placeholders, values not suitable for text), never a list of wanted entries; the skip list is named in code and in the spec, with examples. (decision log 2026-11-12, "minus a skip list per format"; decisions 129, 235)
- [ ] **`mapped_metadata`**: what we compute (frame count, scan size) or a reader maps to standard names, a second, labelled section; where it disagrees with the original, the original wins. (230; Merlin, EMPAD)
- [ ] **Not suitable for text** is one shared check: `modama_crawler.formats.values.textual(value)` (more than 16 items, more than 1,000 characters, control characters, bytes, arrays that are not numbers). Don't write your own. (@weber 2026-11-12)
- [ ] **Credentials are skipped, best effort**: a value that `modama_crawler.formats.values.credential(name, value)` flags (a name such as `password`, `token`, `api_key`; a text such as `POSTGRES_PASSWORD=…`, `--requirepass …`, a URL with a password, `Basic …`) stays out of `original_metadata` and the summary line, counted in `mapped_metadata`; a record is seen by more people than the file. (review of change `common-structured`, 2026-11-12)
- [ ] **Empty values are kept** in the values, as the file has them (`""`, `[]`). (decision 161; `test_extract.py` of Merlin, EMPAD, K2IS)
- [ ] **A test with an entry nobody has seen**: it must arrive in `original_metadata`. (the skip-list rule above)
- [ ] **The summary line**: a few chosen entries as found, text bare, a number after its name (`Exposure Time (s) 2.0`), 0 placeholders left out, no words or units of ours, with two exceptions: a number whose reader gives no unit says so, "(unit unknown)" (@weber, 2026-11-11; EM README, "Values and units"; EMPAD's exposure time); a document whose metadata can't be read because it is encrypted has the summary line "(encrypted)" (@weber, 2026-11-12, 242b; office: PDF, OpenDocument). It is the only positive list. (`dm.HEADLINE`; 228, 231)
- [ ] **The values become the record's second description**, one `name: value` line each, sorted by name, empty values left out there: names and values must read well that way. (234, change `tags-in-the-record`)
- [ ] **Read only what is needed**: headers, never a whole large file; the tree is on NFS, about 1.5 million files, some of hundreds of GB. Unbuffered reads, or a 64 KiB buffer with readahead off for a reader that reads in tiny pieces (README, "Pitfalls", F12, F14). `extract` runs with a time limit. Count the bytes read in a test (`modama_formats_em.testing.rchar`). (@weber 2026-11-12; block files: the header plus one buffer)
- [ ] **Time-zone independent output**: a date and time as the file writes it, without a reader's conversion to the local time zone, and a test under another `TZ`. (`modama_formats_em.blockfile`, `test_the_acquisition_time_as_written`)
- [ ] **Recognition by content where names lie**: a glob plus magic, a subtype (`sub-class-of`) where one exists, and `d.not_of_type` to fall back to the type the file has without its name rule. ("A file that is not of its name's type" above; DM by header whatever the name, `.blo` without `IMGBLO`)
- [ ] **Fixtures**: public test data with licence and source in `fixtures.toml`, or generated at test time by the software that writes the format; small (cut to what the rules and extractor read if need be, the cut in `validity`); no copyrighted content without a licence. (Fixtures above; @weber 2026-11-12: "Use publicly available test data")
- [ ] **One test per spec scenario**, named after it. (`tests/test_mime.py`; AGENTS.md, "Writing tests")
- [ ] **No version to raise**: any change to the installed code changes the extractor identity, and the next crawl extracts every dataset again. Expect that cost with every merge. (`identity.py`, "Extracting metadata" above)
- [ ] **Look at real files** with `modama-chain browse` before and after. (`python/search-chain/README.md`, "browse")
