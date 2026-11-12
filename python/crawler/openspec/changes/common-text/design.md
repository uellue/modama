# Design: plain text and markup documents

## D1 The encoding: what the bytes say, Windows-1252 for the rest

A text file rarely says its encoding (a byte order mark, an HTML `<meta charset>`, an Emacs cookie); mostly it has to be detected. The brief named charset-normalizer, the detector `requests` uses, or the BOM and UTF-8 validity. Measured on 2026-11-12 with short samples as found at ER-C (German and French notes, a log with one degree sign), charset-normalizer 3.5.2, chardet 5.2.0 and chardet 7.7.0 (`detect`, default arguments unless noted):

| Sample (bytes as written) | charset-normalizer 3.5.2 | chardet 5.2.0 | chardet 7.7.0 | chardet 7.7.0, `MODERN_WEB` |
|---|---|---|---|---|
| German, Latin-1, two lines | `mac_iceland` | `ISO-8859-9` (Turkish) | `Windows-1252` | `Windows-1252` |
| French, Latin-1, one line | `cp1257` | `ISO-8859-1` | `iso8859-15` | `Windows-1252` |
| English with curly quotes, Windows-1252 | `cp1250` | `Windows-1252` | `Windows-1252` | `Windows-1252` |
| `Größe`, Latin-1, one word | — | `ISO-8859-7` (Greek) | `MacIceland` | `Windows-1252` |
| 20 ASCII log lines, then one Latin-1 `°` | — | `ISO-8859-1` | `Windows-1252` | `Windows-1252` |
| 1 MiB ASCII, then one Latin-1 `ä` | — | — | `utf-8` (`max_bytes=len`) | — |
| 4,000 ASCII bytes, then UTF-8 cut inside `ö` | — | — | `Windows-1250` (`max_bytes=len`) | — |
| UTF-8, UTF-8 with BOM, UTF-16 with BOM, ASCII | right | — | right | right |
| 1,024 bytes 0..255 (binary) | none | — | none | none |

The best of them, chardet 7.7.0 restricted to the encodings browsers support (`EncodingEra.MODERN_WEB`), then named the fixture's two lines `Probe 3, Raumtemperatur` / `Änderung: Blende 50 µm, 20 °C` in Windows-1252 `CP949` (Korean: `Än`, `µm` and `°C` are valid CP949 pairs). On 466 notes of one to three such lines, Windows-1252, it decoded 51 wrongly (`big5hkscs`, `Windows-1251`, `Big5`, `CP949`, `Windows-1250`), 17 when restricted to single-byte encodings, 132 with its defaults. A detector's guess on a short note is a coin with many sides, and a wrong name in a description is a false statement.

So the bytes decide where they can, exactly, and what they cannot decide is decoded as the web decodes unlabelled text in German and English locales (`head.encoding`):

1. A BOM: `UTF-32` (`FF FE 00 00`, `00 00 FE FF`), `UTF-8-SIG` (`EF BB BF`), `UTF-16` (`FF FE`, `FE FF`): chardet's names, which Python's codecs read (the BOM is not text).
2. A NUL byte: not text, no encoding (`null`). UTF-16 without a BOM falls here too; the tools seen write one.
3. The head decodes as ASCII: `ascii`; as UTF-8, with a sequence cut by the head's end allowed: `utf-8`.
4. Else `Windows-1252`, the default encoding the HTML standard suggests "for compatibility with legacy content" for all locales its table does not list, German and English among them (WHATWG HTML, 13.2.3.2 "Determining the character encoding", checked 2026-11-12); it reads Latin-1 text as Latin-1 reads it, but for the C1 control codes 0x80 to 0x9F.

No detector library then: no dependency for it. A Cyrillic or Japanese file in a legacy encoding is named `Windows-1252` and its title garbled; none is known in the tree (Q in the hand-over, with chardet 7.7.0, 0BSD, as the alternative).

## D2 Bounds

- `HEAD` = 1 MiB (1,048,576 bytes): the bytes read, one `read` of `HEAD + 1` on an unbuffered file, so that the extra byte says whether the head is the whole file. Encoding, lines, BibTeX entries and the HTML head come from it.
- `PARSE` = 65,536 characters of the decoded head: what markdown-it-py, docutils and pylatexenc parse. Measured on synthetic documents (2026-11-12): markdown-it-py 2.9 s for 1 MiB, 0.14 s for 64 KiB; docutils 28 s and 0.55 s; pylatexenc 5.6 s and 0.3 s (1.4 s on the first call). Front matter, a document title and docinfo, and a LaTeX preamble are at the start of a file.
- HTML is parsed with `html.parser` from the head in pieces of 65,536 characters until the head ends (`</head>` or `<body>`), so the 229 MB report costs 1 MiB.
- BibTeX: bibtexparser parses the decoded head (0.3 s for 1 MiB, 13,246 entries); a cut head is cut before its last line that starts with `@`, so that the entry cut in two is neither counted nor reported as broken.

## D3 Where values go

`original_metadata` is what the file says about itself, in the reader's names: the record shows it as its second description. `mapped_metadata` is what we compute: encoding, lines, first heading, entries and keys. A plain text file, a log and a README say nothing about themselves that is not body, so their `original_metadata` is empty.

Names: the YAML front matter's keys, joined with dots, lists of mappings numbered (`authors[0].name`); docutils' names for docinfo (`author`, `date`, `revision`, a generic field by its name as written); HTML `title`, `lang`, `meta.<name>` where `<name>` is the `name`, `http-equiv`, `property` or `itemprop` attribute, in that order, and `meta.charset`, a name met twice keeping both values as a list; LaTeX the macro's name.

## D4 One dataset per file, priority 20

The core already types all these files (`freedesktop.org.xml`), so the area has no MIME rules. A format makes one dataset of each file of its type, like the core's single files but with an extractor. Priority 20: a format of another area or collection that claims a text file as a member of its dataset (a sidecar) must run first. The runner then warns that the file is already claimed, as it does for any two claims: the formats cannot see each other's claims (Q).
