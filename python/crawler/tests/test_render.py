"""XML rendering details (the `records-cli` spec's comments), and oai_dc validity."""

from datetime import UTC, datetime

from conftest import validate_oai
from lxml import etree
from modama_crawler.formats import Dataset, Extracted, Extraction
from modama_crawler.records import build
from modama_crawler.render import comment, element, list_records


def test_a_record_with_description_and_subjects_is_valid_oai_dc():
    dataset = Dataset(
        anchor="/scan.dm4",
        members=("/scan.dm4",),
        type="application/octet-stream",
        format="em/dm",
        size=1234,
        extraction=Extraction(
            "em/dm", "1", "", Extracted(["voltage 300 kV"], ["TEM", "Titan"], {})
        ),
    )
    identifier, metadata = build(dataset)
    validate_oai(
        list_records(
            "http://localhost/oai",
            [(identifier, datetime(2024, 1, 1, tzinfo=UTC), metadata)],
        )
    )


def rendered(text: str) -> str:
    container = element("ListRecords")
    comment(container, text)
    return etree.tostring(container, encoding="unicode")


def test_comment_survives_dashes():
    # A comment may not contain "--" or end with "-"; runs of dashes are the trap
    for text in ("a--b", "a---b", "a----b", "scan---final.tif: WARNING: x", "ends-"):
        out = rendered(text)
        assert "<!--" in out and "-->" in out
    assert "<!-- a- - -b -->" in rendered("a---b")
    assert "<!-- ends- -->" in rendered("ends-")
