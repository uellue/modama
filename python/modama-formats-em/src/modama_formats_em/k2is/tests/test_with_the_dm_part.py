"""K2IS together with the DM part, under the MIME database of every installed collection (spec formats/k2is, change recognition-checks-content)."""

import shutil
from pathlib import Path

from modama_crawler.walk import walk

import modama_formats_em

DM3 = Path(__file__).parents[2] / "dm/tests/fixtures/stem_image_dm3/test_STEM_image.dm3"


def test_a_lone_tag_file_with_the_dm3_header(mime_database, tmp_path):
    # Decision 183: accepted like a DM4 one, flagged as a file of interest to be
    # reviewed by hand; em/dm3 (60, after em/k2is at 61) does not see it
    shutil.copy(DM3, tmp_path / "config.gtg")
    result = walk(tmp_path, modama_formats_em.COLLECTION.formats)
    (d,) = result.datasets
    assert (d.type, d.format, d.basis) == (
        "application/x.dm-gtg",
        "",
        "single file; em/k2is: file of interest: DM3 .gtg, review by hand",
    )
    assert result.all_warnings() == []
