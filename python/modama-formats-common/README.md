# modama-formats-common

Common file formats for the modama crawler (`python/crawler/`), as the format collection `common`: images, Python data science (notebooks, NumPy, HDF5, Zarr and their derivatives), office documents, plain text and structured data. Install it next to the crawler and the crawler finds it through the entry point group `modama.formats`; its format ids start with `common/`.

| Format | Recognised as | Extracted |
|---|---|---|
| Office Open XML (`office`) | `.docx`, `.docm`, `.pptx`, `.xlsx`, `.xlsm` by name, a single file each (`common/docx` …) when it starts with a ZIP header; a misnamed file (a text file, an encrypted `.docx`, which is an OLE2 file) gets the type its content gives | a summary line of title, creator, created, application, pages or slides as the file writes them (`My Title, EJ04325S, 2011-07-29T16:52:00Z, Microsoft Office Word, Pages 1`). Values: every entry of the property parts the package's relationships name, as `core.<element>`, `app.<element>`, `custom.<name>`, as text (`original_metadata`); a presentation's slide count, a workbook's sheets with their dimensions by openpyxl's read-only mode, which also reads the shared strings (the cells' texts) and each sheet up to its `<dimension>`, not called when such a part is over 16 MiB (`mapped_metadata`). Never pictures or the document's other parts |
| OpenDocument (`office`) | `.odt`, `.odp`, `.ods` as the core types them, a single file each (`common/odt` …) when it starts with a ZIP header | a summary line of title, initial creator, creation date, generator and page count (`Apache Tika, Bart Hanssens, 2009-10-05T19:04:01, OpenOffice.org/3.1…, page-count 2`). Values: every child of `meta.xml`'s `office:meta` by its local name, attributes as `<name>.@<attribute>`, user-defined fields as `user-defined.<name>` (`original_metadata`); `encrypted` (`mapped_metadata`; an encrypted document's `meta.xml` is not read) |
| PDF (`office`) | `.pdf` as the core types it, a single file (`common/pdf`) when `%PDF-` is in its first 1,024 bytes | a summary line of the Info dictionary's title, author, creation date, creator, producer and the page count (`Apache Tika - Apache Tika, Bertrand Delacrétaz, D:20070915110231+02'00', Firefox, Mac OS X 10.4.10 Quartz PDFContext, pages 1`). Values: every Info entry as `Info.<key>` and every XMP property as `XMP.<prefix>:<name>` (`original_metadata`); header, catalog version, page count, `encrypted` (`mapped_metadata`). By pypdf, given only a file with `%%EOF` at its end and at most 32 MiB to read; an encrypted file with the empty user password, as viewers open it; never the pages' content |
| Legacy Word, PowerPoint, Excel (`office`) | `.doc`, `.ppt`, `.pps`, `.xls` as the core types them, a single file each (`common/doc` …) when it starts with the OLE2 signature (an RTF file named `.doc` is RTF) | a summary line of title, author, creation time, application, page or slide count (`My Title, EJ04325S, 2010-10-05T09:03:00Z, Microsoft Office Word, num_pages 1`). Values: every property of the SummaryInformation and DocumentSummaryInformation sets under olefile's names, strings decoded with the file's code page, but the binary ones (`original_metadata`); user-defined properties are not read |
| Office lock files (`office`) | `~$name` as `application/x-ms-owner`, `.~lock.name#` as `application/x.libreoffice-lock`, by name, whatever the locked document's extension | nothing |

None yet: each area (`image`, `pydata`, `office`, `text`, `structured`) is a subpackage added by its own change, with one import and one entry in `PARTS` in `src/modama_formats_common/__init__.py`, and its rows here.

## Values and units: what the file says

The principles of `python/modama-formats-em/README.md`, "Values and units: what the driver says", hold here too: an extractor shows what the file or its reader says, without editorializing (no rounding, no unit guessed or converted); what the file says comes first, every entry minus a skip list per format, never a list of wanted entries; values not suitable for text (too large, binary) are left out by the one check every collection shares, `modama_crawler.formats.values.textual`. The checklist for writing a format is `python/crawler/src/modama_crawler/formats/TEMPLATE.md`.

## Setup and tests

```bash
uv pip install --python ~/.venv/bin/python -e python/crawler[test] -e python/modama-formats-common[test]
cd python/modama-formats-common && pytest src
```

Each area is a subpackage of `src/modama_formats_common/` with its MIME rules, fixtures and tests, written as `python/crawler/src/modama_crawler/formats/TEMPLATE.md` describes; the crawler's pytest plugin runs them. Fixtures are public test data with their licence and source in `fixtures.toml`, or generated at test time.

## Licence

MIT (`LICENSE`).
