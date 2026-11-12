# Proposal

## Why

The tree holds office documents beside the instrument data (October listing, 2026-10-15): `.pdf` 862, `.docx` 151, `.pptx` 149, `.xlsx` 26, `.odt` 20, `.odp` 8, `.ods` 2, legacy `.doc` 4, `.ppt` 4, `.xls` 3, `.pps` 1, and 13 lock files (`~$name.pptx`, `~$name.pdf`, `.~lock.name.docx#`). The core recognises them by name (and some by content), but their records say nothing but type, size and folder. @weber, 2026-11-12, for the night: "develop more format libraries … Apply all lessons from EM formats as far as applicable. Use publicly available test data", with the established readers (python-docx, python-pptx, openpyxl, odfpy, pypdf, olefile) named in the brief.

Leans of the brief, taken in as assumptions (where this proposal deviates, it says why):

- **Readers.** openpyxl (read-only), pypdf and olefile as named. **Deviation:** python-docx, python-pptx and odfpy are not used: each loads every part of the package on open, measured: `Presentation()` and `Document()` read 27,076,272 and 27,081,105 bytes of a 27 MB file (one 27 MB picture), where reading `docProps/core.xml` through `zipfile` reads 146,252 (2026-11-12, `python-pptx` 1.0.2, `python-docx` 1.2.0); odfpy's `load()` reads every picture likewise. The tree's largest `.pptx` is 474 MB (median 4.3 MB), the largest `.odp` 168 MB. The property parts are read instead with `zipfile` and defusedxml, as the brief allows ("else read that one XML part with defusedxml"); this also keeps every entry the parts have rather than the libraries' fixed property lists (TEMPLATE.md: "never a list of wanted entries"). Recorded in `BACKLOG.md`, "Sync with upstream", as *worked around here*.
- **Values.** `original_metadata` is every entry of the format's metadata (OOXML `docProps/core.xml`, `app.xml`, `custom.xml`; ODF `meta.xml`; PDF Info dictionary and XMP; OLE2 SummaryInformation and DocumentSummaryInformation) minus one skip list per family; `mapped_metadata` what we or a reader compute (slide count, sheet dimensions, page count, PDF header, encrypted). Dates as the file writes them.
- **Recognition by content**: the OOXML types have a name rule only, ODF, PDF and OLE2 a name rule that decides alone; each format checks the first bytes and drops a misnamed file to the type its content gives.
- **Lock files**: recognised by name, no extraction. The core types them as the documents they lock (a `~$x.pptx` is a PowerPoint presentation by its glob); this change gives them types of their own.
- **Macro-enabled variants**: the core types `.docm` and `.xlsm` as subtypes of `.docx` and `.xlsx`; they get the same extraction (fixtures exist). `.pptm` has no public fixture and none is in the tree: left out.
- **Fixtures**: Apache Tika's test documents (Apache-2.0), written by Word, PowerPoint, Excel, OpenOffice.org, Firefox, Apache FOP; generated at test time where none exists (lock files, an AES-encrypted PDF by pypdf, misnamed files).

## What Changes

- `python/modama-formats-common/src/modama_formats_common/office/`: formats `common/docx`, `docm`, `pptx`, `xlsx`, `xlsm`, `odt`, `odp`, `ods`, `doc`, `ppt`, `xls`, `pdf`; `office.xml` with the lock-file types `application/x-ms-owner` (Apache Tika's name, PRONOM fmt/473) and `application/x.libreoffice-lock`; tests, fixtures, expected results.
- `python/modama-formats-common/`: one import and one `PARTS` entry, rows in the README's table, dependencies `defusedxml`, `openpyxl`, `pypdf[crypto]`, `olefile`, pinned.
- `python/crawler/BACKLOG.md`, "Sync with upstream": python-docx, python-pptx and odfpy load whole packages; olefile's user-defined properties are paired by position.

Behaviour towards the user: the records of office documents and PDFs start with a summary line of their title, author, dates, application and page or slide count as the file writes them, and carry their metadata as a second description (`name: value` lines). Lock files get types of their own ("Microsoft Office owner file", "LibreOffice lock file") instead of the type of the document they lock. A file named like an office document that is not one gets the type its content gives (a text file named `.docx` is `text/plain`).

Out of scope: text content of documents (no page text, no cell data); `.pptm`, templates (`.dotx`, `.potx`, `.xltx`), `.odg`, `.rtf` (15 in the tree) and Outlook `.msg` (588) (questions in the hand-over); user-defined properties of legacy OLE2 files (olefile, see BACKLOG); decryption with a password (only the empty user password that viewers try).

Serves: R25 (Dublin Core from the file system and the files), decisions 129, 230, 234, 235 and the skip-list rule of 2026-11-12, TEMPLATE.md's checklist "Lessons from the EM formats".

## Capabilities

### New Capabilities
- `formats/office`: office documents and PDFs, recognised by content, described by their metadata.

### Modified Capabilities
None.

## Impact

- `python/modama-formats-common/`: the subpackage `office`, `__init__.py`, `README.md`, `pyproject.toml`.
- `python/crawler/BACKLOG.md`.
- New dependencies: defusedxml, openpyxl, pypdf with its `crypto` extra (cryptography), olefile. No migration, no change of the core.
