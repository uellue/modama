"""The trace's rules with canned inputs (chain-trace spec); the stores themselves are tested in the e2e stack."""

from datetime import UTC, datetime, timedelta

import pytest
from modama_chain.chain import (
    BEFORE_HARVEST_WINDOW,
    DIFFERS,
    MISSING,
    OK,
    STALE,
    WARN,
    Stage,
    diverging,
    freshness,
    harvest_stage,
    search_stage,
)
from modama_chain.crawler import Keys, Run
from modama_chain.warehouse import Event, HarvestRun, IndexRun, local_id

T0 = datetime(2026, 11, 5, 8, tzinfo=UTC)


def at(minutes: int) -> datetime:
    return T0 + timedelta(minutes=minutes)


def harvest(id, minutes_from, minutes_until, status="closed"):
    start = None if minutes_from is None else at(minutes_from)
    return HarvestRun(id, status, at(minutes_until), start, at(minutes_until))


def crawl(start, end, outcome="finished"):
    return Run(at(start), at(end), at(end), outcome, 1, 1, 1, 1, None, timedelta(0))


URL = "https://example.org/browse/?path=/a.txt"


# A dataset that is not the first hit is a warning


def test_rank_1_is_ok():
    assert search_stage("/a.txt", URL, [URL, "x"], True).state == OK


def test_rank_below_1_is_a_warning_with_the_first_hit():
    stage = search_stage("/a.txt", URL, ["x", URL], True)
    assert (
        stage.state == WARN
        and "rank 2" in stage.detail
        and "first hit x" in stage.detail
    )
    assert (
        diverging([Stage("tree", OK), stage]) is None
    )  # does not change the exit status


def test_absent_from_the_hits_is_missing():
    assert search_stage("/a.txt", URL, ["x"], True).state == MISSING


def test_a_hit_the_crawler_no_longer_publishes_is_stale():
    assert search_stage("/a.txt", URL, [URL], False).state == STALE


# A record dated before the harvest window is flagged


def test_datestamp_before_the_last_harvests_window():
    stage = harvest_stage("/late.txt", at(0), None, harvest("h2", 30, 60))
    assert stage.state == BEFORE_HARVEST_WINDOW
    assert "2026-11-05T08:00:00Z" in stage.detail and "08:30:00Z" in stage.time


def test_after_the_last_harvest_is_not_harvested_yet():
    stage = harvest_stage("/new.txt", at(90), None, harvest("h2", 30, 60))
    assert (stage.state, stage.detail) == (
        MISSING,
        "not harvested yet: datestamp after the last harvest",
    )


def test_in_the_window_of_the_last_harvest_but_not_harvested_is_lost():
    # the next incremental harvest starts at the last until, so this record is never asked for
    stage = harvest_stage("/a.txt", at(45), None, harvest("h2", 30, 60))
    assert stage.state == BEFORE_HARVEST_WINDOW


def test_the_harvester_cuts_the_window_to_seconds():
    last = HarvestRun(
        "h2", "closed", at(60), at(30), at(60) + timedelta(microseconds=700000)
    )
    assert harvest_stage("/a.txt", at(60), None, last).state == MISSING


def test_an_older_version_harvested_differs():
    old = Event(harvest("h1", None, 30), at(10), False, None)
    stage = harvest_stage("/a.txt", at(70), old, harvest("h2", 30, 60))
    assert stage.state == DIFFERS


def test_an_errored_event_is_not_a_harvest():
    event = Event(harvest("h1", None, 30), at(10), False, "parse error")
    stage = harvest_stage("/a.txt", at(70), event, harvest("h1", None, 30))
    assert (stage.state, stage.detail) == (DIFFERS, "error: parse error")


def test_the_current_version_harvested_is_ok():
    event = Event(harvest("h1", None, 30), at(10), False, None)
    stage = harvest_stage("/a.txt", at(10), event, harvest("h2", 30, 60))
    assert (stage.state, stage.time) == (OK, "start .. 2026-11-05T08:30:00Z")


def test_harvested_but_no_longer_published_is_stale():
    event = Event(harvest("h1", None, 30), at(10), False, None)
    assert harvest_stage("/a.txt", None, event, harvest("h2", 30, 60)).state == STALE


# The first diverging stage is marked


def test_first_stage_missing_after_one_that_has_the_item():
    states = [OK, OK, OK, MISSING, MISSING]
    assert diverging([Stage(str(i), s) for i, s in enumerate(states)]) == 3


def test_a_renamed_file_diverges_at_the_first_stale_stage():
    states = [MISSING, MISSING, MISSING, STALE, STALE, STALE, STALE]
    assert diverging([Stage(str(i), s) for i, s in enumerate(states)]) == 3


def test_a_path_in_no_stage_is_consistent():
    assert diverging([Stage(str(i), MISSING) for i in range(7)]) is None


# The status states the freshness time


def test_a_complete_chain():
    t, _ = freshness(
        [crawl(0, 5)],
        [harvest("h1", None, 10)],
        [IndexRun("success", None, None, "h1")],
    )
    assert t == at(0)


def test_a_crawl_that_is_not_harvested_yet():
    crawls = [crawl(20, 25), crawl(0, 5)]
    t, _ = freshness(
        crawls, [harvest("h1", None, 10)], [IndexRun("success", None, None, "h1")]
    )
    assert t == at(0)


def test_a_failed_harvest():
    harvests = [harvest("h1", None, 10), harvest("h2", 10, 30, status="failed")]
    crawls = [crawl(20, 25), crawl(0, 5)]
    t, _ = freshness(crawls, harvests, [IndexRun("success", None, None, "h1")])
    assert t == at(0)


def test_a_harvest_not_indexed_stops_the_chain():
    harvests = [harvest("h1", None, 10), harvest("h2", 10, 30), harvest("h3", 30, 40)]
    crawls = [crawl(20, 25), crawl(0, 5)]
    index = [
        IndexRun("success", None, None, "h1"),
        IndexRun("failed", None, None, "h2"),
        IndexRun("success", None, None, "h3"),
    ]
    assert freshness(crawls, harvests, index)[0] == at(0)


def test_no_indexed_harvest():
    t, reason = freshness([crawl(0, 5)], [harvest("h1", None, 10)], [])
    assert t is None and "indexed" in reason


# Keys rebuilt for paths the crawler no longer has follow the crawler's rules


@pytest.mark.parametrize(
    "path",
    [
        "/a.txt",
        "/c d.txt",
        "/e:f.txt",
        "/g+h%.txt",
        "/ü/ß.txt",
        "/" + "x" * 300,
        "/" + "ä" * 120,
    ],
)
def test_rebuilt_keys_match_the_crawlers(path):
    records = pytest.importorskip("modama_crawler.records")
    keys = Keys(f"oai:{records.OAI_NAMESPACE}:", records.BROWSE_URL)
    assert keys.identifier(path) == records.oai_identifier(path)
    assert keys.url(path) == records.browse_url(path)


def test_the_harvester_keeps_the_part_after_the_last_colon():
    assert local_id("oai:er-c-data-mgmt.fz-juelich.de:/e%3Af.txt") == "/e%3Af.txt"


# Output layout A (@weber 2026-11-05): keys once, then short stage lines


# The crawler line shows the dataset's basis


def test_a_text_file_named_like_a_k2is_tag_file():
    from modama_chain.chain import crawler_detail
    from modama_chain.crawler import Holding

    basis = "single file; em/k2is: not application/x.dm-gtg, no DM header"
    found = Holding("/notes.gtg", False, basis)
    assert crawler_detail(found, True, True) == f"dataset; basis: {basis}"


def test_a_plain_file_and_a_member():
    from modama_chain.chain import crawler_detail
    from modama_chain.crawler import Holding

    plain = Holding("/a.txt", False, "single file")
    assert crawler_detail(plain, True, True) == "dataset; basis: single file"
    member = Holding("/scan/h.xml", True, "header names the raw file")
    assert (
        crawler_detail(member, True, False)
        == "member of /scan/h.xml; basis: header names the raw file"
    )
    # No dataset holds it: nothing to show
    assert crawler_detail(None, False, True) == "keys rebuilt from the path"


# "The trace names the identity behind a description" (change extractor-identity)

H0, H1 = "6d881430e7c8" + "0" * 52, "77b1e2d4a0c9" + "1" * 52


def test_a_description_from_the_current_installation():
    from modama_chain.chain import crawler_detail
    from modama_chain.crawler import Holding

    found = Holding("/a.dm4", False, "*.dm4", "em/dm4", H0)
    assert crawler_detail(found, True, True, H0) == (
        "dataset; basis: *.dm4; extracted by em/dm4 under 6d881430e7c8, "
        "the last crawl's (current)"
    )


def test_a_description_left_from_another_installation():
    from modama_chain.chain import crawler_detail
    from modama_chain.crawler import Holding

    found = Holding("/a.dm4", False, "*.dm4", "em/dm4", H1)
    assert crawler_detail(found, True, True, H0).endswith(
        "extracted by em/dm4 under 77b1e2d4a0c9, the last crawl's is 6d881430e7c8: they differ"
    )
    # a label from before identities, quoted as runs shows it
    old = Holding("/a.dm4", False, "*.dm4", "em/dm4", "4")
    assert 'under "4", the last crawl\'s is 6d881430e7c8' in crawler_detail(
        old, True, True, H0
    )


# "The status shows the last crawl's re-extraction"


def test_after_a_crawl_that_extracted_again():
    from modama_chain.chain import crawl_line

    run = Run(
        at(0), at(5), at(5), "finished", 2, 3, 3, 1, None, timedelta(0), H0,
        [{"format": "em/dm4", "from": H1, "datasets": 2, "changed": 1, "differences": []}],
    )  # fmt: skip
    assert crawl_line(run).endswith(
        "3 datasets, 1 records changed; identity 6d881430e7c8, 2 extracted again, "
        "1 result changed"
    )
    # A crawler database from before identities: the line as before
    before = Run(at(0), at(5), at(5), "finished", 2, 3, 3, 1, None, timedelta(0))
    assert crawl_line(before).endswith("3 datasets, 1 records changed")


def test_trace_lines_show_the_keys_once_and_wrap_long_details():
    from modama_chain.cli import trace_lines

    stages = [
        Stage(
            "tree",
            OK,
            "/a.txt",
            "ctime 2026-11-05T10:00:00Z",
            "mtime 2026-11-05T09:00:00Z",
        ),
        Stage("crawler", OK, "oai:x:/a.txt", "2026-11-05T10:00:01Z", "dataset"),
        Stage(
            "harvest",
            BEFORE_HARVEST_WINDOW,
            "/a.txt",
            "start .. 2026-11-05T10:05:00Z",
            "word " * 40,
        ),
    ]
    lines = trace_lines("/a.txt", stages)
    assert lines[:3] == ["/a.txt", "  oai id    oai:x:/a.txt", ""]
    assert (
        lines[3]
        == "  tree      ok                     ctime 2026-11-05T10:00:00Z  mtime 2026-11-05T09:00:00Z"
    )
    assert lines[5].startswith("> harvest   BEFORE-HARVEST-WINDOW  start .. ")
    assert all(len(line) <= 100 for line in lines)
    assert lines[6].startswith(" " * 12 + "word")
