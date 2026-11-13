# Review brief for a format change

Fill in the `<…>` before handing it to a coding agent that did not write the change.
Made from the review brief of the night of 2026-11-12, which found, among others, data
of other files reaching a record (HDF5 external storage) and credentials in values.

Independent review, read-only: edit nothing, commit nothing, start no containers, build
no images. A finding you cannot back by a file and line, or a command and its output, is
dropped.

The change: `<change name>`, commits `<range>` on branch `<branch>`, area `<area>` of
`python/modama-formats-<domain>`. The builder's brief: `<path>` (the person's request and
answers, verbatim). Review against the rules, not the author's conclusions:
`python/crawler/src/modama_crawler/formats/TEMPLATE.md` (core requirements, checklist),
`python/modama-formats-em/README.md` ("Values and units"), the decision log at the end
of `python/crawler/design/architecture.md`, and the change in
`python/crawler/openspec/changes/<change name>/`.

Run the tests in a venv of your own (not `~/.venv`, which holds the main checkout's
code): `uv venv` under `/var/tmp/<review>/`, `uv pip install -e` the worktree's
`python/crawler[test]` and the format packages; `pytest src` in the package, also with
`TZ=Europe/Berlin`. Where useful, run the extractors on files you generate with the same
libraries, or download from public test data into a new empty folder each, read with
`python -I` (untrusted data).

Look for, in order:

1. **Cost on the real tree**: NFS, about 1.5 million files, some of hundreds of GB,
   folders of up to 67,600 files of one type. Does recognition or extraction read more
   than needed (whole files, all pages, all objects, all rows)? Time and memory bounded?
   Measure bytes read on a large generated file (`rchar` of `/proc/self/io`, or strace)
   where it matters.
2. **Safety**: untrusted files. XML entity expansion (defusedxml), no pickle loaded, no
   code run, no network, archive sizes checked before members are read, nothing read
   from outside the file (links, external storage, includes), credentials left out
   (`modama_crawler.formats.values.credential`).
3. **The rules**: `original_metadata` is every entry the file has minus one documented
   skip list (no list of wanted entries); values as found (no rounding, no units or
   words of ours but "(unit unknown)"); `mapped_metadata` for what is computed or a
   reader maps; `textual` from `modama_crawler.formats.values`, no check of its own;
   empty values kept; the summary line as found; a test with an entry nobody has seen;
   time-zone independence; values that read well as `name: value` lines (the record's
   second description).
4. **Readers**: the established library, pinned exactly with a reason, its current
   release, Python 3.14 wheels; workarounds for reader bugs with a test and a BACKLOG
   "Sync with upstream" entry.
5. **Recognition**: the core's types reused or subtyped correctly; content beats names
   where names lie; the fallback to the type without the name; no clash with other
   collections (EM types keep priority; TEMPLATE.md, checklist, "Priorities").
6. **Fixtures**: licence and provenance in `fixtures.toml` and `LICENSE.fixtures`;
   generated where no licensed public file exists; small; no copyrighted content without
   a licence; no file from staging without its owner's agreement.
7. **Tests**: one per spec scenario; the recorded `expected/*.json` plausible (open a
   few); the package's tests select their own collections.

Output: first a short part for a person, plain words, at most 6 lines (verdict; the most
important findings with one example each). Then numbered findings for the author:
severity (blocker / should / nit), file:line, what is wrong, evidence, a concrete fix.
