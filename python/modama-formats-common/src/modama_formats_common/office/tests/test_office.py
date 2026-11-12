"""Office documents and PDFs (spec formats/office), one test per scenario.

Run with -s to see each description and the bytes the extractor read.
"""

import os
import time
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from modama_crawler.formats import Dataset, Extracted, Extraction
from modama_crawler.records import description
from modama_crawler.testing import recognise
from modama_crawler.walk import walk

from modama_formats_common.office import ole, pdf
from modama_formats_common.office.common import MAX_PART, OverBudget

FIXTURES = Path(__file__).parent / "fixtures"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def rchar() -> int:
    """Bytes this process has read so far, from /proc/self/io (Linux)."""
    for line in Path("/proc/self/io").read_text().splitlines():
        key, _, value = line.partition(":")
        if key == "rchar":
            return int(value)
    raise RuntimeError("no rchar in /proc/self/io")


@dataclass
class Described:
    dataset: Dataset
    extracted: Extracted
    description: str
    bytes_read: int

    @property
    def original(self) -> dict:
        return self.extracted.values["original_metadata"]

    @property
    def mapped(self) -> dict:
        return self.extracted.values["mapped_metadata"]


def crawled(ct, tree: Path) -> list[Described]:
    """Recognise a tree with the part's formats and run each dataset's extractor in this process, as its record describes it."""
    formats = {f.id: f for f in ct.collection.formats if f.has_extractor}
    out = []
    for d in walk(tree, ct.collection.formats).datasets:
        fmt = formats.get(d.format)
        if fmt is None:
            continue
        fmt.extract(d, str(tree))  # once first: rchar counts the reads of imports too
        before = rchar()
        extracted = fmt.extract(d, str(tree))
        read = rchar() - before
        d = replace(d, extraction=Extraction(fmt.id, "", d.stamp, extracted))
        out.append(Described(d, extracted, description(d), read))
        print(f"{d.anchor}: {out[-1].description!r}, {read} bytes read of {d.size}")
    return out


def described(ct, fixture: str, tmp_path: Path) -> Described:
    """The one extracted dataset of a fixture."""
    (one,) = crawled(ct, ct.materialise(fixture, tmp_path))
    return one


def only(result) -> Dataset:
    (d,) = result.datasets
    return d


def repacked(src: Path, dst: Path, member: str, change) -> Path:
    """A copy of the ZIP src at dst with member's bytes changed by change(bytes) -> bytes."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item)
            zout.writestr(item, change(data) if item.filename == member else data)
    return dst


# Recognition


def test_a_word_document(collection_tests, tmp_path):
    d = only(recognise(collection_tests, "word_docx", tmp_path))
    assert (d.type, d.format, d.basis) == (DOCX, "common/docx", "ZIP header")


def test_macro_enabled_variants(collection_tests, tmp_path):
    docm = only(recognise(collection_tests, "word_docm", tmp_path / "a"))
    xlsm = only(recognise(collection_tests, "excel_xlsm", tmp_path / "b"))
    assert (docm.type, docm.format) == (
        "application/vnd.ms-word.document.macroenabled.12",
        "common/docm",
    )
    assert (xlsm.type, xlsm.format) == (
        "application/vnd.ms-excel.sheet.macroenabled.12",
        "common/xlsm",
    )
    # Described as their counterparts
    assert described(collection_tests, "word_docm", tmp_path / "c").original
    assert described(collection_tests, "excel_xlsm", tmp_path / "d").mapped == {
        "sheets": {"Sheet1": "A1:A2", "Sheet2": "A1:A1", "Sheet3": "A1:A1"}
    }


@pytest.mark.parametrize(
    ("fixture", "mime", "reason"),
    [
        ("text_docx", "text/plain", f"common/docx: not {DOCX}, no ZIP header"),
        ("text_pdf", "text/plain", "common/pdf: not application/pdf, no PDF header"),
        (
            "text_odt",
            "text/plain",
            "common/odt: not application/vnd.oasis.opendocument.text, no ZIP header",
        ),
        (
            "rtf_doc",
            "application/rtf",
            "common/doc: not application/msword, no OLE2 header",
        ),
    ],
)
def test_a_text_file_named_like_an_office_document(
    collection_tests, tmp_path, fixture, mime, reason
):
    d = only(recognise(collection_tests, fixture, tmp_path))
    assert (d.type, d.format) == (mime, "")
    assert d.basis == f"single file; {reason}"


def test_an_empty_file_named_like_a_presentation(collection_tests, tmp_path):
    d = only(recognise(collection_tests, "empty_pptx", tmp_path))
    assert d.format == ""
    assert not d.type.startswith("application/vnd.openxmlformats")
    assert crawled(collection_tests, tmp_path / "empty_pptx") == []


def test_a_password_protected_word_document(collection_tests, tmp_path):
    d = only(recognise(collection_tests, "protected_docx", tmp_path))
    assert (d.type, d.format) == ("application/x-ole-storage", "")


def test_lock_files_beside_documents(collection_tests, tmp_path):
    result = recognise(collection_tests, "lock_files", tmp_path)
    assert {d.anchor: (d.type, d.format) for d in result.datasets} == {
        "/~$report.docx": ("application/x-ms-owner", ""),
        "/~$slides.pdf": ("application/x-ms-owner", ""),
        "/.~lock.report.odt#": ("application/x.libreoffice-lock", ""),
    }
    assert crawled(collection_tests, tmp_path / "lock_files") == []


# Office Open XML


def test_a_representative_word_document(collection_tests, tmp_path):
    docx = described(collection_tests, "word_docx", tmp_path)
    assert docx.description.startswith(
        "My Title, EJ04325S, 2011-07-29T16:52:00Z, Microsoft Office Word, Pages 1; "
    )
    assert docx.original["core.lastModifiedBy"] == "Etienne Jouvin"
    assert docx.original["app.Company"] == "EDF-DIT"
    assert docx.original["app.TitlesOfParts"] == ["My Title"]
    assert docx.original["custom.MyCustomString"] == "MyStringValue"
    assert docx.original["custom.myCustomNumber"] == "3"


@pytest.fixture
def berlin(monkeypatch):
    """The process in the time zone Europe/Berlin while the test runs."""
    monkeypatch.setenv("TZ", "Europe/Berlin")
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def test_dates_as_the_file_writes_them(collection_tests, tmp_path, berlin):
    docx = described(collection_tests, "word_docx", tmp_path)
    assert docx.original["core.created"] == "2011-07-29T16:52:00Z"
    assert docx.original["custom.MyCustomDate"] == "2010-12-30T23:00:00Z"


def test_empty_values_are_kept(collection_tests, tmp_path):
    docm = described(collection_tests, "word_docm", tmp_path)
    assert docm.original["core.title"] == ""
    assert docm.extracted.summary[0] == "Allison, Timothy B."


def test_a_presentation(collection_tests, tmp_path):
    pptx = described(collection_tests, "powerpoint_pptx", tmp_path)
    assert pptx.description.startswith(
        "title, Allison, Timothy B., 2015-09-30T17:58:06Z, "
        "Microsoft Office PowerPoint, Slides 1; "
    )
    assert pptx.mapped == {"slides": 1}


def test_a_workbook(collection_tests, tmp_path):
    xlsx = described(collection_tests, "excel_xlsx", tmp_path)
    assert xlsx.mapped == {
        "sheets": {"Feuil1": "A1:D22", "Feuil2": "A1:A1", "Feuil3": "A1:A1"}
    }


def test_only_the_property_parts_are_read(collection_tests, tmp_path):
    src = FIXTURES / "powerpoint_pptx" / "testPPT_comment.pptx"
    big = tmp_path / "tree" / "big.pptx"
    repacked(src, big, "", bytes)
    with zipfile.ZipFile(big, "a") as z:
        z.writestr("ppt/media/image9.png", os.urandom(20_000_000))
    (pptx,) = crawled(collection_tests, tmp_path / "tree")
    assert pptx.dataset.size > 20_000_000
    assert pptx.mapped == {"slides": 1}
    assert pptx.bytes_read < 1_000_000


def test_a_workbook_with_large_cell_data(collection_tests, tmp_path):
    src = FIXTURES / "excel_xlsx" / "testEXCEL.xlsx"
    big = MAX_PART + 1

    def padded(data: bytes) -> bytes:
        return data.replace(b"</sst>", b" " * (big - len(data)) + b"</sst>")

    repacked(src, tmp_path / "tree" / "big.xlsx", "xl/sharedStrings.xml", padded)
    (xlsx,) = crawled(collection_tests, tmp_path / "tree")
    assert xlsx.mapped == {
        "sheets not read": f"xl/sharedStrings.xml: {big} bytes, more than {MAX_PART}"
    }
    assert xlsx.original["core.title"] == "Simple Excel document"
    assert xlsx.bytes_read < 1_000_000


def test_a_broken_package(collection_tests, tmp_path):
    d = only(recognise(collection_tests, "truncated_docx", tmp_path))
    assert d.format == "common/docx"
    fmt = next(f for f in collection_tests.collection.formats if f.id == d.format)
    with pytest.raises(zipfile.BadZipFile):
        fmt.extract(d, str(tmp_path / "truncated_docx"))


def test_an_entry_nobody_has_seen(collection_tests, tmp_path):
    src = FIXTURES / "word_docx" / "testWORD_custom_props.docx"
    repacked(
        src,
        tmp_path / "tree" / "new.docx",
        "docProps/app.xml",
        lambda b: b.replace(
            b"</Properties>", b"<FooVendorSetting>7</FooVendorSetting></Properties>"
        ),
    )
    (docx,) = crawled(collection_tests, tmp_path / "tree")
    assert docx.original["app.FooVendorSetting"] == "7"


# OpenDocument


def test_a_representative_text_document(collection_tests, tmp_path):
    odt = described(collection_tests, "writer_odt", tmp_path)
    assert odt.description.startswith(
        "Apache Tika, Bart Hanssens, 2009-10-05T19:04:01, "
        "OpenOffice.org/3.1$Unix OpenOffice.org_project/310m19$Build-9420, "
        "page-count 2; "
    )
    assert odt.original["keyword"] == ["Apache", "Lucene", "Tika"]
    assert odt.original["editing-duration"] == "PT02H03M24S"
    assert odt.original["user-defined.Editor"] == "Bart Hanssens"
    assert odt.original["user-defined.Info 2"] == ""
    assert odt.mapped == {"encrypted": False}


def test_a_spreadsheet_and_a_presentation(collection_tests, tmp_path):
    ods = described(collection_tests, "calc_ods", tmp_path / "a")
    odp = described(collection_tests, "impress_odp", tmp_path / "b")
    assert ods.original["document-statistic.@cell-count"] == "4"
    assert odp.original["document-statistic.@object-count"] == "25"


def test_an_encrypted_document(collection_tests, tmp_path):
    odt = described(collection_tests, "encrypted_odt", tmp_path)
    assert odt.mapped == {"encrypted": True}
    assert odt.original == {}


def test_an_attribute_nobody_has_seen(collection_tests, tmp_path):
    src = FIXTURES / "writer_odt" / "testODFwithOOo3.odt"
    repacked(
        src,
        tmp_path / "tree" / "new.odt",
        "meta.xml",
        lambda b: b.replace(
            b"</office:meta>",
            b'<foo:setting xmlns:foo="urn:foo" foo:level="7">high</foo:setting>'
            b"</office:meta>",
        ),
    )
    (odt,) = crawled(collection_tests, tmp_path / "tree")
    assert odt.original["setting"] == "high"
    assert odt.original["setting.@level"] == "7"


# PDF


def test_a_representative_pdf(collection_tests, tmp_path):
    pdf = described(collection_tests, "pdf_info", tmp_path)
    assert pdf.description.startswith(
        "Apache Tika - Apache Tika, Bertrand Delacrétaz, D:20070915110231+02'00', "
        "Firefox, Mac OS X 10.4.10 Quartz PDFContext, pages 1; "
    )


def test_custom_entries_and_xmp_structures(collection_tests, tmp_path):
    pdf = described(collection_tests, "pdf_custom", tmp_path)
    values = pdf.original
    assert values["Info.Custom Property"] == "Custom Value"
    assert values["Info.Custom Array"] == ["Array Entry 1", "Array Entry 2"]
    assert values["XMP.xmp:CreateDate"] == "2010-06-30T14:01:54+02:00"
    assert values["XMP.bib:title"] == [
        "default title of EP1000000A1",
        "english title of EP1000000A1",
        "german title of EP1000000A1",
        "french title of EP1000000A1",
    ]
    assert values["XMP.bib:representative.bib:rep-name"] == "name of the representative"
    assert values["XMP.bib:priorities[1].rdf:value"] == "number of priority n"


def test_an_encrypted_pdf_that_opens_without_a_password(collection_tests, tmp_path):
    rc4 = described(collection_tests, "pdf_owner_password", tmp_path / "a")
    aes = described(collection_tests, "pdf_aes", tmp_path / "b")
    assert rc4.mapped["encrypted"] and aes.mapped["encrypted"]
    assert rc4.mapped["pages"] == aes.mapped["pages"] == 1
    assert aes.original["Info.Title"] == "Encrypted with AES-256"


def test_an_encrypted_pdf_that_needs_a_password(collection_tests, tmp_path):
    pdf = described(collection_tests, "pdf_user_password", tmp_path)
    assert pdf.mapped == {"header": "%PDF-1.4", "encrypted": True}
    assert pdf.original == {}
    assert pdf.extracted.summary == []


def large_pdf(path: Path) -> bytes:
    """A one-page PDF of 20 MB, nearly all of it an attached file; its bytes."""
    from pypdf import PdfWriter

    path.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "Large"})
    writer.add_attachment("data.bin", os.urandom(20_000_000))
    with open(path, "wb") as f:
        writer.write(f)
    return path.read_bytes()


def test_only_the_metadata_is_read(collection_tests, tmp_path):
    large_pdf(tmp_path / "tree" / "large.pdf")
    (described_pdf,) = crawled(collection_tests, tmp_path / "tree")
    assert described_pdf.dataset.size > 20_000_000
    assert described_pdf.original["Info.Title"] == "Large"
    assert described_pdf.bytes_read < 1_000_000


def extracted_reading(path: Path) -> tuple[object, int]:
    """What pdf.extract gives or raises for path, and the bytes it read."""
    before = rchar()
    try:
        outcome = pdf.extract(str(path))
    except Exception as error:  # noqa: BLE001  the error is the outcome tested
        outcome = error
    return outcome, rchar() - before


def test_a_cut_off_pdf(tmp_path):
    data = large_pdf(tmp_path / "large.pdf")
    cut = tmp_path / "cut.pdf"
    cut.write_bytes(data[:-3000])
    error, read = extracted_reading(cut)
    assert isinstance(error, ValueError)
    assert "no %%EOF in the last 1,024 bytes" in str(error)
    assert read < 1_000_000


def test_a_pdf_whose_recovery_would_read_all_of_it(tmp_path, monkeypatch):
    data = large_pdf(tmp_path / "large.pdf")
    offset = data.rindex(b"startxref") + len(b"startxref\n")
    end = data.index(b"\n", offset)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(data[:offset] + b"12345" + data[end:])
    monkeypatch.setattr(pdf, "BUDGET", 4 * 1024 * 1024)
    error, read = extracted_reading(broken)
    assert isinstance(error, OverBudget), error
    assert read < 5 * 1024 * 1024


def test_a_header_after_other_bytes(collection_tests, tmp_path):
    src = (FIXTURES / "pdf_info" / "testPDF.pdf").read_bytes()
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "prefixed.pdf").write_bytes(b"X" * 100 + b"\n" + src)
    (prefixed,) = crawled(collection_tests, tree)
    assert prefixed.dataset.format == "common/pdf"
    assert prefixed.mapped["header"] == "%PDF-1.3"


def test_a_reference_cycle_in_the_info_dictionary(collection_tests, tmp_path):
    from pypdf import PdfWriter
    from pypdf.generic import NameObject

    tree = tmp_path / "tree"
    tree.mkdir()
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_metadata({"/Title": "Cycle"})
    root = writer.root_object.indirect_reference
    writer._info.get_object()[NameObject("/Foo")] = root
    with open(tree / "cycle.pdf", "wb") as f:
        writer.write(f)
    (cycle,) = crawled(collection_tests, tree)
    assert cycle.original["Info.Title"] == "Cycle"
    # The value's own reference is followed (to the catalog), the catalog's not
    foo = cycle.original["Info.Foo"]
    assert foo["/Type"] == "/Catalog"
    assert foo["/Pages"].endswith(" 0 R")


# Legacy OLE2


def test_a_representative_word_97_document(collection_tests, tmp_path):
    doc = described(collection_tests, "word_doc", tmp_path)
    assert doc.description.startswith(
        "My Title, EJ04325S, 2010-10-05T09:03:00Z, Microsoft Office Word, num_pages 1; "
    )
    assert doc.original["company"] == "EDF-DIT"
    assert doc.original["heading_pairs"] == ["Titre", 1]


def test_a_mac_code_page(collection_tests, tmp_path):
    ppt = described(collection_tests, "powerpoint_ppt", tmp_path)
    assert ppt.original["codepage"] == 10000
    assert ppt.original["title"] == "Sample Powerpoint Slide"
    assert ppt.extracted.summary[-1] == "slides 1"


def test_a_utf_8_code_page(tmp_path):
    data = (FIXTURES / "word_doc" / "testWORD_custom_props.doc").read_bytes()
    cp1252 = bytes.fromhex("02000000e404")  # VT_I2, 1252
    # In each section: SummaryInformation, DocumentSummaryInformation's two
    assert data.count(cp1252) == 3
    patched = tmp_path / "utf8.doc"
    patched.write_bytes(data.replace(cp1252, bytes.fromhex("02000000e9fd")))  # 65001
    values = ole.extract(str(patched)).values["original_metadata"]
    assert values["codepage"] == 65001
    assert values["title"] == "My Title"
    assert values["company"] == "EDF-DIT"


def test_user_defined_properties(collection_tests, tmp_path):
    xls = described(collection_tests, "excel_xls", tmp_path)
    assert xls.original["creating_application"] == "Microsoft Excel"
    assert not any("MyCustom" in k for k in xls.original)


# What is left out, and the summary line


def test_binary_values(collection_tests, tmp_path):
    ppt = described(collection_tests, "powerpoint_ppt", tmp_path)
    assert "thumbnail" not in ppt.original
    assert ppt.original["presentation_target"] == "On-screen Show"


def test_a_value_too_long_for_text(collection_tests, tmp_path):
    titles = b"".join(b"<vt:lpstr>T%d</vt:lpstr>" % i for i in range(17))
    src = FIXTURES / "word_docx" / "testWORD_custom_props.docx"
    repacked(
        src,
        tmp_path / "tree" / "many.docx",
        "docProps/app.xml",
        lambda b: b.replace(
            b'<vt:vector size="1" baseType="lpstr"><vt:lpstr>My Title</vt:lpstr>',
            b'<vt:vector size="17" baseType="lpstr">' + titles,
        ),
    )
    (docx,) = crawled(collection_tests, tmp_path / "tree")
    assert "app.TitlesOfParts" not in docx.original
    assert docx.original["app.Company"] == "EDF-DIT"


def test_a_count_of_0(collection_tests, tmp_path):
    src = FIXTURES / "word_docx" / "testWORD_custom_props.docx"
    repacked(
        src,
        tmp_path / "tree" / "zero.docx",
        "docProps/app.xml",
        lambda b: b.replace(b"<Pages>1</Pages>", b"<Pages>0</Pages>"),
    )
    (docx,) = crawled(collection_tests, tmp_path / "tree")
    assert docx.original["app.Pages"] == "0"
    assert not any(p.startswith("Pages") for p in docx.extracted.summary)
