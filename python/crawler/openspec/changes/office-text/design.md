# Design: an office document's text in its record (`office-text`)

Facts looked up on 2026-11-14 (PyPI's JSON API, the code host's repository API), measurements in a throwaway venv (Python 3.14, the versions below) on two self-made documents written by python-docx and python-pptx, each with one 20 MB noise PNG, and on the office area's Tika fixtures. Bytes read are `/proc/self/io` `rchar`, as `modama_crawler.testing.bytes_read` counts them, imports warmed up first.

## D1 The converter

| Candidate | Release (date), licence | Reads media? | Dependencies | Maintenance |
|---|---|---|---|---|
| MarkItDown (Microsoft) | 0.1.9 (2026-10-21), MIT; `requires-python <3.15,>=3.10` | yes: its Word path is mammoth, which embeds pictures as data URIs; its PowerPoint path is python-pptx, which loads every part. 40,686,911 bytes read for the 20 MB `.docx` (the file read twice) | core: beautifulsoup4, certifi, charset-normalizer, defusedxml, **magika** (1.0.3, Apache-2.0, 16 MiB wheel, needs **onnxruntime** 1.32.0, 26 MiB wheel, with numpy, protobuf, flatbuffers), markdownify, requests; extras `docx` (mammoth, lxml), `pptx` (python-pptx) | very active (pushed 2026-11-07), pre-1.0 |
| mammoth (`.docx`) | 1.13.0 (2026-09-26), BSD-2-Clause | pictures yes by default (data URIs); with `convert_image` not reading them, 530,317 bytes; on the proxy (D2) none | cobble 0.1.4 (BSD) | active (pushed 2026-09-26); external file access off by default since its fix, off in 1.13.0 |
| markdownify (HTML to Markdown) | 1.2.3 (2026-06-30), MIT | n/a (a string) | beautifulsoup4 4.15.0 (MIT), six | active (pushed 2026-11-11) |
| python-pptx | 1.0.2 (2024-08-07), MIT | yes: `Presentation()` read 20,346,359 bytes of the 20 MB deck; on the proxy 134,847 | lxml 6.1.3 (BSD-3, 5 MiB wheel), XlsxWriter (BSD-2), Pillow (here already), typing-extensions | quiet: no release or push since 2024-08; stable API |
| pandoc (binary) | 3.14 (2026-11-12), GPL-2.0 | its Word reader collects the media into its media bag (not measured) | one static binary, 34 MiB packed (`pypandoc-binary` 1.17 wheel 32 MiB) | very active |
| docx2python | 3.7.2 (2026-10-28), MIT | read 132,528 bytes of the 20 MB `.docx` for `.text` | lxml, paragraphs, typing-extensions | active, one maintainer |

Choice (L1): mammoth + markdownify for Word, python-pptx on the proxy for PowerPoint. They are the libraries MarkItDown itself uses for these two formats; taking them directly avoids magika and onnxruntime, which MarkItDown's package imports at import time although we would never call them (every extraction worker would load them; not measured), and MarkItDown's cap below Python 3.15. What we write ourselves: the proxy (D2) and the walk over a presentation's slides, about 50 lines in the shape of MarkItDown's `PptxConverter` (slide title as `#`, text frames, tables, notes), without its HTML comment per slide and its picture handling. mammoth's own Markdown output is deprecated by its author ("Generating HTML and using a separate library to convert the HTML to Markdown is recommended"), hence markdownify. pandoc is left out for its licence in the image, its size and a process per document; docx2python for its output (nested lists, no Markdown), which would leave the renderer to us.

Alternative kept open: our own walk over the WordprocessingML and PresentationML with defusedxml (no dependency, the area's way for the property parts), about 150 lines; against the standing rule while established libraries exist.

## D2 The proxy: only the XML parts

An OOXML package is a ZIP whose `[Content_Types].xml` gives each part's content type (by extension, `Default`, or by part name, `Override`). The extractor opens the file as the area does (`common.opened`, 64 KiB buffer, readahead off), reads `[Content_Types].xml` with defusedxml, and writes a ZIP in memory (`ZIP_STORED`, no recompression) with every part whose content type ends in `xml` (the parts, relationships, themes, charts' XML) as it is, and every other part present but empty. Media, embedded packages and PDFs (`word/embeddings/`, `ppt/embeddings/`), OLE objects, macros (`vbaProject.bin`), fonts and thumbnails are thus never read, by the rule on types, not by folder names. Empty parts keep the converters working: mammoth and python-pptx open them without error (both measured on the 20 MB documents; the rendered text was the same as from the original but for the pictures).

| 20 MB documents | bytes read |
|---|---|
| proxy of the `.docx` | 135,764 |
| proxy + MarkItDown's Word path (mammoth + markdownify) on it | 135,764 |
| proxy of the `.pptx` + python-pptx + MarkItDown's slide walk on it | 134,862 |
| python-pptx on the original `.pptx` | 20,346,359 |
| MarkItDown's Word path on the original `.docx` | 40,686,911 |

Safety: the converters parse the XML with their own parsers, mammoth with `xml.dom.minidom` (expat 2.9.0 here, which limits entity expansion), python-pptx with lxml and `resolve_entities=False`. Since OOXML never needs a DTD, a kept part whose first 1,024 bytes hold `<!DOCTYPE` stops the rendering (L9) rather than reaching them. A part that expands to gigabytes (a ZIP bomb in an XML part) is stopped by the worker's 4 GiB address space and 60 s, as for every extractor; no limit of ours (L5).

## D3 What the rendering keeps

Measured with MarkItDown's code paths on the self-made documents and the fixtures:

- Word (self-made): `Lamella preparation` (style Title: mammoth's default style map has no entry for it, so a plain line; L3 adds `p[style-name='Title'] => h1:fresh`), `# Milling`, `Thinning at **30 kV**, then *5 kV* cleaning.`, `* first step` / `* second step`, `1. one`, a pipe table; the picture as `![](data:image/png;base64...)`, to be left out; a comment's text (`A reviewer's private remark`) not shown.
- Tracked changes (a paragraph with `<w:ins>INSERTED</w:ins>` and `<w:del>DELETED</w:del>`): `Kept INSERTED`; the deleted text never appears.
- `testWORD_macros.docm` (Tika): `The **quick** *brown* fox.`; `testWORD_custom_props.docx`: `Document content`.
- PowerPoint (self-made): `# Drift correction`, `Cross-correlation per frame`, `Sub-pixel by upsampling`, `### Notes:`, `Speaker note: mention the 2019 data`, `# Results`, and the picture as `![noise.png](Picture2.jpg)`, to be left out. `testPPT_comment.pptx` (Tika): `# title`, `subtitle`; its comment not shown.
- `testWORD_truncated.docx`: `BadZipFile`, as the metadata's extraction already fails today.

Speaker notes are in (L3): they are part of the file as every reader of the deck sees it in PowerPoint, and they often say what a slide only shows. Comments and deleted text are out: they are remarks about the document, often by other people, not its text.

## D4 Into the record, and the cut

The rendering goes into `values["text"]` and is the record's second description by the records requirement of `text-as-written`; nothing in `records.py` changes. A rendering over 4,096 characters is shortened by `written.shown_text` (first and last lines, about 2,000 characters each, `… N characters left out …` between), the one rule `text-as-written` has for a text of ours; for a deck its last slides are often "Thank you" or "Questions", and an outline first (all headings, then text) may serve better: a next step once real records are seen (Out of scope). `values["text"]` is the shown text, not the whole rendering: one stored string holds at most `MAX_STRING` characters, as for every format.

With a text the property parts' `name: value` lines leave the record (L7): `text-as-written` decided "only the text" (its L2) so that the same content does not fill the embedding's 512 tokens twice. For office documents the two are not the same content: company, template, custom properties go out of the record. The summary line keeps title, author, dates, application, pages or slides.

## D5 The flag and its channel

"Flag when it goes beyond what we had discussed before": the limits discussed are the per-file read limit of recognition (decision 329: flag past 64 KiB, stop at 1 MiB), the 10 s of `slow extraction` (352), `text-as-written`'s reads (1 MiB head, 16 KiB tail, 80 KiB of a large structured file) and the area's 16 MiB per XML part (`MAX_PART`). The bytes read for the proxy are the measure: they are what the converters will parse, and they are counted as the read limit counts (bytes read from the file, `Budgeted.read_so_far`). 64 KiB would flag almost every document (135 kB for python-docx's empty template with one paragraph); 1 MiB is the read limit's stop, the point where recognition refuses, so "beyond" it is the read I take for "beyond what we had discussed". Alternatives: 64 KiB (flags nearly all), 16 MiB (`MAX_PART`, flags only extremes).

The channel: an `Extracted` holds summary, subjects and values, stored in three columns; a new field would need a migration. So an extractor puts its warnings into `values["warnings"]` (a list of strings, each ending in `; <marker>`), and the crawler warns them at the dataset, from the stored extraction at every crawl, as `_slow` does for `slow extraction` (a reused extraction keeps exactly one of each). Alternatives: (a) only a `mapped_metadata` entry with the bytes read, seen in `browse` and `records --verbose` but not listed by `modama-chain review` (no change of the core, today's fallback); (b) every extraction's bytes read measured in the worker like its seconds, one flag for every format (a stored field, a migration: a next step).

## D6 Failures

The rendering runs after the property parts are read; an exception of the converter (or the `<!DOCTYPE` stop of D2) keeps the metadata, gives no `text`, so the record keeps the tag lines, and puts the message into `mapped_metadata["text not rendered"]`, as `sheets not read` does for a workbook. The extraction does not fail: a failure is retried by every crawl (decision 185), a document the converter cannot render would be converted again every night. A package that is not a ZIP fails as today.

## D7 Tests and fixtures

Public fixtures: Tika's at the pinned commit `a40d54f6…` (`fixtures.toml`): `testWORD_macros.docm`, `testWORD_custom_props.docx`, `testPPT_comment.pptx` (in the area already); `testComment.docx` (11,019 bytes) and `testPPT_embeddedMP3.pptx` (84,434 bytes, a real embedded audio file) to add. Written at test time by the software that writes the format (A1): a `.docx` with title, headings, list, bold, table and a 20 MB picture by python-docx, a `.pptx` with notes and a 20 MB picture by python-pptx (both new dependencies anyway; python-docx 1.2.0 for the tests only, MIT, a test extra). Tracked changes: no Tika file with "track", "change", "ins" or "del" in its name at that commit, so a reproducer written at test time (`testWORD_custom_props.docx` with one insertion and one deletion added to `word/document.xml`, A3); mammoth's own test documents (BSD-2) may hold one, not checked. A document of more than 1 MiB of XML for the flag, written at test time.

## Questions for @weber

- **Q1** The new dependencies: mammoth 1.13.0, markdownify 1.2.3, python-pptx 1.0.2, with cobble, beautifulsoup4, soupsieve, six, lxml, XlsxWriter, typing-extensions; python-docx 1.2.0 for the tests. Lean: yes (D1).
- **Q2** Speaker notes in the text (D3). Lean: yes.
- **Q3** The tag lines leave the record of a document with text (D4, L7). Lean: yes, as `text-as-written`.
- **Q4** The flag at 1 MiB of XML read, marker `large document text`, through `values["warnings"]` (D5). Lean: yes; fallback for tonight if the core is not to change today: the number in `mapped_metadata` only.
- **Q5** A long rendering as head and tail (D4). Lean: yes for now, an outline after seeing real records.
