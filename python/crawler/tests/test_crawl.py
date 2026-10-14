"""Crawl a directory tree and serve the result."""

import os
import pwd

from conftest import DC, OAI
from modama_crawler.database import crawl_and_populate
from modama_crawler.records import browse_url, oai_identifier


def test_crawl_and_serve(conn, oai, tmp_path):
    (tmp_path / "notes.txt").write_text("notes")
    (tmp_path / "sub dir").mkdir()
    (tmp_path / "sub dir" / "run 12:30.txt").write_text("run")
    (tmp_path / "bell\x07.txt").write_text("bell")
    # Not valid UTF-8, can't be stored and is skipped
    os.close(os.open(os.fsencode(tmp_path) + b"/latin1-\xe4.txt", os.O_CREAT))

    assert crawl_and_populate(conn, tmp_path)["records_changed"] == 3

    path = "/sub dir/run 12:30.txt"
    document = oai(
        verb="GetRecord", identifier=oai_identifier(path), metadataPrefix="oai_dc"
    )
    assert document.findtext(f".//{DC}title") == path
    assert document.findtext(f".//{DC}identifier") == browse_url(path)
    assert document.findtext(f".//{DC}creator") == pwd.getpwuid(os.getuid()).pw_name
    assert document.findtext(f".//{DC}format") == "text/plain"

    # Nothing changed, nothing to publish
    assert crawl_and_populate(conn, tmp_path)["records_changed"] == 0

    # Deleted files disappear from the repository
    (tmp_path / "notes.txt").unlink()
    crawl_and_populate(conn, tmp_path)
    document = oai(verb="ListIdentifiers", metadataPrefix="oai_dc")
    paths = ["/bell\x07.txt", "/sub dir/run 12:30.txt"]
    found = [e.text for e in document.iter(f"{OAI}identifier")]
    assert sorted(found) == sorted(oai_identifier(p) for p in paths)
