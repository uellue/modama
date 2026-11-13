"""Direct Electron acquisitions with the whole em collection, under the MIME database of every installed collection (spec formats/de)."""

import shutil

from modama_crawler.walk import walk

import modama_formats_em

from .generate import ACQUISITION, lone_movie
from .test_recognize import ACQUISITION as MEMBERS


def test_a_movie_without_its_info_file(mime_database, tmp_path):
    # A single file of the MRC part, and no warning of em/de
    lone_movie(tmp_path / "lone")
    result = walk(tmp_path / "lone", modama_formats_em.COLLECTION.formats)
    (d,) = result.datasets
    assert (d.anchor, d.type, d.format) == (
        "/20241021_00405_movie.mrc",
        "application/x.mrc",
        "em/mrc",
    )
    assert result.all_warnings() == []


def test_the_members_are_not_offered_to_later_formats(mime_database, tmp_path):
    # em/de (62) runs before em/mrc (61): it is not offered the MRC members, so
    # the crawl warns of nothing (bug 311, change em-de D2)
    shutil.copytree(ACQUISITION, tmp_path / "acq")
    result = walk(tmp_path / "acq", modama_formats_em.COLLECTION.formats)
    (d,) = result.datasets
    assert (d.format, set(d.members)) == ("em/de", MEMBERS)
    assert result.all_warnings() == []
