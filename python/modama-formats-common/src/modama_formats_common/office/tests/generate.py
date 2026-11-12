"""Fixture generators: lock files, misnamed and empty files, and a PDF encrypted with AES-256 by pypdf."""

from pathlib import Path


def owner_file(user: str) -> bytes:
    """A Microsoft Office owner file's layout as Apache Tika's magic for it describes it
    (tika-mimetypes.xml, application/x-ms-owner): the user name's length, the name in
    53 bytes, the length again and a zero byte, then the name in UTF-16; 162 bytes, as
    the owner files of .docx and .pdf in the October listing measure."""
    n = len(user)
    data = bytes([n]) + user.encode("ascii").ljust(53, b"\0") + bytes([n, 0])
    return (data + user.encode("utf-16-le")).ljust(162, b"\0")


def lock_files(target: Path) -> None:
    """Office's owner files beside a document and a PDF, LibreOffice's lock file beside a document."""
    target.mkdir(parents=True)
    (target / "~$report.docx").write_bytes(owner_file("modama"))
    (target / "~$slides.pdf").write_bytes(owner_file("modama"))
    (target / ".~lock.report.odt#").write_text(
        ",modama,modama-host,12.11.2026 22:13,file:///home/modama/.config/libreoffice/4;"
    )


def text_docx(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "notes.docx").write_text("hello\n")


def text_pdf(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "notes.pdf").write_text("hello\n")


def rtf_doc(target: Path) -> None:
    """An RTF file named .doc, as Word saves "Rich Text" under a .doc name on request."""
    target.mkdir(parents=True)
    (target / "letter.doc").write_text("{\\rtf1\\ansi Hello\\par}\n")


def empty_pptx(target: Path) -> None:
    target.mkdir(parents=True)
    (target / "empty.pptx").write_bytes(b"")


def pdf_aes(target: Path) -> None:
    """A one-page PDF with a title, encrypted by pypdf with AES-256, an empty user password and an owner password."""
    from pypdf import PdfWriter

    target.mkdir(parents=True)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "Encrypted with AES-256"})
    writer.encrypt(user_password="", owner_password="owner", algorithm="AES-256")
    with open(target / "aes.pdf", "wb") as f:
        writer.write(f)
