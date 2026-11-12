"""Office documents and PDFs: single-file datasets, recognised by their first bytes, described by their metadata (spec formats/office).

The core types these files by name. Each format checks the first bytes of
the files of its type and drops a misnamed one to the type its content gives
(Directory.not_of_type). The formats of the ZIP packages run first, then
those of OLE2, then PDF, so that a dropped file reaches the format of its
content in the cases seen (an encrypted .docx is an OLE2 file). Lock files
get types of their own by name (office.xml), without a format. Extraction
reads the metadata only: ooxml, odf, pdf, ole.
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Entry, Format

from . import odf, ole, ooxml, pdf

HERE = Path(__file__).parent
# The core's magic for PDF: %PDF- within the first 1,024 bytes
PDF_WINDOW = 1024


def head(d: Directory, e: Entry, n: int) -> bytes | None:
    """The first n bytes of e, or None if it cannot be read: then it keeps its type, the crawl warns at
    it, and the directory is recognised again next crawl, while the other files' outcome stands."""
    try:
        return d.read(e, n)
    except OSError as error:
        d.cannot_read(e, error)
        return None


class Office(Format):
    """A file of the format's type, as one dataset when its first bytes are `signature`."""

    signature = b""
    basis = ""

    def found(self, d: Directory, e: Entry) -> bool | None:
        """Whether e starts with the signature; None if it cannot be read."""
        data = head(d, e, len(self.signature))
        return None if data is None else data == self.signature

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            match self.found(d, e):
                case True:
                    yield Dataset(anchor=e.rel, basis=self.basis)
                case False:
                    d.not_of_type(e, f"no {self.basis}")


class Package(Office):
    """An Office Open XML package, described by its property parts."""

    priority = 62
    signature = b"PK\3\4"
    basis = "ZIP header"

    def extract(self, dataset: Dataset, root: str):
        return ooxml.extract(root + dataset.anchor)


class Docx(Package):
    type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    reacts_to = frozenset({type})


class Docm(Package):
    # In lower case, as the MIME database gives it (freedesktop.org writes macroEnabled)
    type = "application/vnd.ms-word.document.macroenabled.12"
    reacts_to = frozenset({type})


class Pptx(Package):
    type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    reacts_to = frozenset({type})

    def extract(self, dataset: Dataset, root: str):
        return ooxml.extract(root + dataset.anchor, ooxml.slides)


class Xlsx(Package):
    type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    reacts_to = frozenset({type})

    def extract(self, dataset: Dataset, root: str):
        return ooxml.extract(root + dataset.anchor, ooxml.sheets)


class Xlsm(Xlsx):
    type = "application/vnd.ms-excel.sheet.macroenabled.12"
    reacts_to = frozenset({type})


class OpenDocument(Office):
    """An OpenDocument package, described by its meta.xml."""

    priority = 62
    signature = b"PK\3\4"
    basis = "ZIP header"

    def extract(self, dataset: Dataset, root: str):
        return odf.extract(root + dataset.anchor)


class Odt(OpenDocument):
    type = "application/vnd.oasis.opendocument.text"
    reacts_to = frozenset({type})


class Odp(OpenDocument):
    type = "application/vnd.oasis.opendocument.presentation"
    reacts_to = frozenset({type})


class Ods(OpenDocument):
    type = "application/vnd.oasis.opendocument.spreadsheet"
    reacts_to = frozenset({type})


class Legacy(Office):
    """A legacy Word, PowerPoint or Excel file (OLE2), described by its property sets."""

    priority = 61
    signature = bytes.fromhex("d0cf11e0a1b11ae1")
    basis = "OLE2 header"

    def extract(self, dataset: Dataset, root: str):
        return ole.extract(root + dataset.anchor)


class Doc(Legacy):
    type = "application/msword"
    reacts_to = frozenset({type})


class Ppt(Legacy):
    type = "application/vnd.ms-powerpoint"
    reacts_to = frozenset({type})


class Xls(Legacy):
    type = "application/vnd.ms-excel"
    reacts_to = frozenset({type})


class Pdf(Office):
    """A PDF, described by its Info dictionary and XMP."""

    type = "application/pdf"
    reacts_to = frozenset({type})
    priority = 60
    signature = b"%PDF-"
    basis = "PDF header"

    def found(self, d: Directory, e: Entry) -> bool | None:
        # At the start as a rule; the window only for a file that has none there
        match super().found(d, e):
            case False:
                data = head(d, e, PDF_WINDOW)
                return None if data is None else self.signature in data
            case found:
                return found

    def extract(self, dataset: Dataset, root: str):
        return pdf.extract(root + dataset.anchor)


COLLECTION = Collection(
    "office",
    [
        Docx(),
        Docm(),
        Pptx(),
        Xlsx(),
        Xlsm(),
        Odt(),
        Odp(),
        Ods(),
        Doc(),
        Ppt(),
        Xls(),
        Pdf(),
    ],
    mime_files=(HERE / "office.xml",),
)
