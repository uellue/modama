# Proposal: plain text and markup documents (`common-text`)

## In short

Text files are the most numerous documents in the tree after images: in the October listing 7,287 `.txt` (1.2 GB; four of 100 MiB, 151 over 1 MB), 314 `.log` (159 of 1 to 100 MB), 400 `.html` and 8 `.htm` (one of 229 MB), 194 `.md`, 189 `.bib`, 36 `.rst`, 34 `.tex`, and 21 `README` without extension. Today each is a single file without a description. With this change each becomes a dataset of the `common` collection, described by what the file says about itself, never by its body:

- every text file: the encoding as detected and the line count, for example `utf-8, lines 42`, or `ascii, lines at least 26214` for a log larger than the bound;
- Markdown: the YAML front matter, every key as found, and the first heading;
- reStructuredText: the document title, subtitle and bibliographic field list (docinfo), as docutils reads them;
- HTML: `<title>`, `<html lang>` and every `<meta>` of the head;
- LaTeX: `\documentclass`, `\title`, `\author`, `\date` as written;
- BibTeX: the number of entries and their keys.

Example (a docutils document, from `modama-crawler records`): `Docutils Front-End Tools, David Goodger, 2024-12-04, utf-8, lines 570; ReStructuredText document, 1 file, 16.7 kB, in rst/`.

## Why

@weber, 2026-11-12: "Let's develop more format libraries to be tested tomorrow. Apply all lessons from EM formats as far as applicable. Use publicly available test data", plain text among the five areas; the common brief (`night-formats-brief.md`) names this area's items. Serves R30 (findable by what the data is), R15 (extract from content), R14 (collections as templates).

## What Changes

- A subpackage `text` of `modama-formats-common` with eight formats, one per MIME type the core already gives these files (no MIME rules of its own): `common/text` (`text/plain`), `common/log` (`text/x-log`), `common/readme` (`text/x-readme`), `common/markdown` (`text/markdown`), `common/rst` (`text/x-rst`), `common/html` (`text/html`), `common/tex` (`text/x-tex`), `common/bibtex` (`text/x-bibtex`). Each makes one dataset of each file of its type, at priority 20, after the formats that may claim a text file as a member of their dataset.
- Extraction reads at most the first 1 MiB of a file (`HEAD`, plus one byte to know whether that is all) and parses at most the first 65,536 characters of it for the Markdown, reStructuredText and LaTeX heads (`PARSE`: docutils needs 28 s for 1 MiB, 0.5 s for 64 KiB, measured 2026-11-12).
- New dependencies of `modama-formats-common`, current releases looked up on PyPI on 2026-11-12, all with wheels for Python 3.14: `PyYAML==6.0.3` (MIT), `markdown-it-py==4.3.0` and `mdit-py-plugins==0.7.0` (MIT), `docutils==0.23` (public domain, BSD-2 parts), `pylatexenc==2.11` (MIT), `bibtexparser==2.1.0` (MIT). HTML with Python's `html.parser`.

Behaviour towards the user: a searcher sees text, Markdown, reStructuredText, HTML, LaTeX and BibTeX files with a description that starts with their title, author, encoding and line count where the file has them, and the format's name in `dc:subject`; the record's second description lists the file's own entries (front matter, docinfo, HTML meta, LaTeX title fields). Their datestamps move once. A crawl reads up to 1 MiB of each such file once, at extraction.

## Assumptions and leans (go-ahead with the leans, 2026-11-12)

- **Encoding: what the bytes say, no detector** (design D1, with the evidence; a deviation from the brief's "as detected", Q): a byte order mark names it (`UTF-8-SIG`, `UTF-16`, `UTF-32`); a NUL byte means not text (no encoding); bytes that decode as ASCII or UTF-8 are `ascii` or `utf-8`; anything else is `Windows-1252`, the HTML standard's suggested default for legacy content in German and English locales. charset-normalizer, which the brief named, called short German Latin-1 text `mac_iceland`, French `cp1257` and Windows-1252 `cp1250`; the best detector tried, chardet 7.7.0 restricted to web encodings, decoded one in nine short German notes wrongly (`CP949`, `Big5`, `Windows-1251`).
- **Lines** count the line feeds in the head, plus a last line without one when the whole file was read; a file larger than the head says `lines at least N` (the brief).
- **The body is never a value**: no first line of a `.txt` as its title (the brief's lean; Q), no paragraph, no abstract. The first heading of a Markdown file is the one exception the brief asks for.
- **What the file says** (`original_metadata`): Markdown front matter keys and values as PyYAML reads them, with date and time as written (no conversion to a time zone); rST title, subtitle and docinfo as docutils reads them (its field names); HTML `title`, `lang`, `meta.<name>`; LaTeX `documentclass`, `title`, `author`, `date` as raw LaTeX. **What we compute** (`mapped_metadata`): `encoding`, `lines` or `lines at least`, Markdown `first heading`, BibTeX `entries` or `entries at least` and `keys`. Plain text, logs and READMEs have an empty `original_metadata`: they say nothing about themselves that is not body.
- **One skip list per format**: values not suitable for text (the shared `textual` check) everywhere; HTML also `meta.viewport` (a display setting, as GMS's window settings for DM). No positive list but the summary line.
- **Safety**: docutils runs without file insertion or raw input (`.. include::` is not followed) and without reading a configuration file; YAML is read with the safe loader, flattened to at most 1,000 entries (an alias bomb stays small).
- **Recognition stays by name**: no content check of `.txt` files in recognition (see Out of scope and Q).

## Out of scope

- Content checks in recognition (`d.not_of_type` for a binary file named `.txt`): nobody has met one; four `.txt` files of exactly 100 MiB in a `raw/` folder are candidates to look at with `modama-chain browse` (Q). Extraction reports such a file honestly: no encoding, no lines.
- JSON, TOML, YAML, CSV, XML and INI files (area `structured`); source code (`text/x-python` and the like); Hitachi SEM `.txt` sidecars (`[SemImageFile]`, key=value), which are INI-like instrument metadata (Q).
- TOML front matter (`+++`), Markdown keywords or tags as `dc:subject`, HTML `<link>` elements, LaTeX packages and class options, BibTeX fields: nobody has asked.

## Capabilities

### New Capabilities
- `formats/text`: plain text and markup documents as datasets, and their extraction.

## Impact

- New `python/modama-formats-common/src/modama_formats_common/text/` (formats, tests, fixtures); one import and one `PARTS` entry in `modama_formats_common/__init__.py`; rows in the package's README; dependencies in its `pyproject.toml`.
- The search stack's crawler image needs a rebuild for the new dependencies (main does it later).
