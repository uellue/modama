"""K2IS together with the DM part, under the MIME database of every installed collection (spec formats/k2is, change recognition-checks-content)."""

import shutil
from pathlib import Path

from modama_crawler.walk import walk

import modama_formats_em

DM3 = Path(__file__).parents[2] / "dm/tests/fixtures/stem_image_dm3/test_STEM_image.dm3"


def test_a_lone_tag_file_with_the_dm3_header(mime_database, tmp_path):
    # Decision 147: a lone .gtg needs the DM4 header. A DM3 one is dropped and
    # becomes a DM3 image of em/dm3 (60, after em/k2is at 61). Open question 183
    # (code review finding 2); the lean is to accept DM3 as for .dmw
    shutil.copy(DM3, tmp_path / "config.gtg")
    result = walk(tmp_path, modama_formats_em.COLLECTION.formats)
    (d,) = result.datasets
    assert (d.type, d.format, d.basis) == (
        "application/x.dm3",
        "em/dm3",
        "Digital Micrograph header; em/k2is: not application/x.dm-gtg, no DM4 header",
    )
    assert result.all_warnings() == []
