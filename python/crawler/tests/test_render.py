"""XML rendering details (the `records-cli` spec's comments)."""

from lxml import etree
from modama_crawler.render import comment, element


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
