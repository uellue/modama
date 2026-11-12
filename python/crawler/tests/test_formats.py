"""The runner: how formats are called on one directory (the `recognition` spec)."""

import time

import pytest
from modama_crawler.formats import (
    DIRECTORY,
    BudgetExceeded,
    Collection,
    Dataset,
    Directory,
    Entry,
    Format,
    Result,
    run_post,
    run_pre,
)


def entry(name, mime="text/plain", kind="file", mtime=1.0, uid=7):
    return Entry(name, f"/abs/{name}", f"/{name}", kind, 3, mtime, mtime, uid, mime)


def directory(entries, children=(), phase="post"):
    return Directory(
        "/", "/abs", list(entries), list(children), phase, uid=1, mtime=0.5
    )


class TextPairs(Format):
    """Claims every text file whose name has a `.bak` sibling, with the sibling."""

    type = "x/pair"
    priority = 60
    reacts_to = frozenset({"text/plain"})

    def recognize(self, d):
        for e in d.of_type("text/plain"):
            bak = d.entry(e.name + ".bak")
            if bak:
                yield Dataset(
                    anchor=e.rel, members=(e.rel, bak.rel), basis="has a .bak sibling"
                )


class Greedy(Format):
    type = "x/greedy"
    priority = 40
    reacts_to = frozenset({"text/plain"})

    def recognize(self, d):
        for e in d.of_type("text/plain"):
            yield Dataset(anchor=e.rel, basis="greedy")


class Adopter(Format):
    type = "x/collection"
    priority = 30
    reacts_to = frozenset({DIRECTORY})
    collection = True

    def recognize(self, d):
        if d.phase == "post" and d.children:
            yield Dataset(
                anchor=d.rel,
                parts=tuple(c.anchor for c in d.children),
                basis="adopts children",
            )


def collect(*formats):
    return Collection("t", list(formats)).formats


def test_declaration_is_visible():
    (fmt,) = collect(TextPairs())
    assert (fmt.type, fmt.priority, fmt.reacts_to, fmt.collection, fmt.id) == (
        "x/pair", 60, frozenset({"text/plain"}), False, "t/textpairs",
    )  # fmt: skip


def test_pair_with_basis_and_single_file_fallback():
    d = directory(
        [entry("a.txt"), entry("a.txt.bak", "application/x-trash"), entry("b.txt")]
    )
    datasets, adoptions = run_post(d, collect(TextPairs()), 5.0, 1 << 20)
    by_anchor = {x.anchor: x for x in datasets}
    assert by_anchor["/a.txt"].members == ("/a.txt", "/a.txt.bak")
    assert by_anchor["/a.txt"].basis == "has a .bak sibling"
    assert by_anchor["/a.txt"].format == "t/textpairs"
    assert by_anchor["/b.txt"].type == "text/plain" and by_anchor["/b.txt"].format == ""
    assert "/a.txt.bak" not in by_anchor
    assert adoptions == {}


def test_unknown_file_becomes_octet_stream_dataset():
    d = directory([entry("blob", "application/octet-stream")])
    datasets, _ = run_post(d, [], 5.0, 1 << 20)
    assert [(x.anchor, x.type) for x in datasets] == [
        ("/blob", "application/octet-stream")
    ]


def test_higher_priority_wins_shared_file():
    d = directory([entry("a.txt"), entry("a.txt.bak", "application/x-trash")])
    datasets, _ = run_post(d, collect(Greedy(), TextPairs()), 5.0, 1 << 20)
    assert [x.format for x in datasets] == ["t/textpairs"]
    assert any("already claimed by t/textpairs" in text for _, text in d.warnings)


def test_sibling_format_runs_only_with_its_type_present():
    calls = []

    class Spy(Format):
        type = "x/spy"
        reacts_to = frozenset({"image/png"})

        def recognize(self, d):
            calls.append(d.phase)
            return ()

    run_pre(
        directory([entry("a.txt", None)], phase="pre"), collect(Spy()), 5.0, 1 << 20
    )
    run_post(directory([entry("a.txt")]), collect(Spy()), 5.0, 1 << 20)
    run_post(directory([entry("a.png", "image/png")]), collect(Spy()), 5.0, 1 << 20)
    assert calls == ["post"]


def test_claim_outside_directory_is_rejected():
    class Outside(Format):
        type = "x/out"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            yield Dataset(anchor="/elsewhere/file", basis="nope")

    d = directory([entry("a.txt")])
    datasets, _ = run_post(d, collect(Outside()), 5.0, 1 << 20)
    assert [x.anchor for x in datasets] == ["/a.txt"]
    assert any("anchor is not a member" in text for _, text in d.warnings)


def test_adopting_a_child_sets_its_parent():
    child = Dataset(anchor="/sub", type="x/series", mtime=9.0)
    d = directory([entry("readme.txt")], children=[child])
    datasets, adoptions = run_post(d, collect(Adopter()), 5.0, 1 << 20)
    collection = next(x for x in datasets if x.anchor == "/")
    assert collection.parts == ("/sub",) and adoptions == {"/sub": "/"}
    assert collection.mtime == 9.0 and collection.uid == 1
    assert not collection.warnings


def test_undeclared_nesting_is_warned():
    class NotDeclared(Adopter):
        collection = False

    d = directory([], children=[Dataset(anchor="/sub", type="x/series")])
    datasets, _ = run_post(d, collect(NotDeclared()), 5.0, 1 << 20)
    assert "is not a collection type but adopts /sub" in datasets[0].warnings[0]


def test_read_budget(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    e = Entry(
        "a.txt", str(tmp_path / "a.txt"), "/a.txt", "file", 100, 1, 1, 7, "text/plain"
    )
    d = directory([e])
    d._budget = 64
    assert d.read(e, 64) == b"x" * 64
    with pytest.raises(BudgetExceeded):
        d.read(e, 1)
    with pytest.raises(ValueError):
        d.read(entry("other.txt"), 1)


def test_read_fetches_only_what_is_asked(tmp_path, bytes_read):
    # Field-test finding F12: see test_mime.test_sniffing_reads_only_the_magic
    size = 4 << 20
    (tmp_path / "a.raw").write_bytes(bytes(size))
    e = Entry("a.raw", str(tmp_path / "a.raw"), "/a.raw", "file", size, 1, 1, 7, None)
    d = directory([e])
    d._budget = size
    before = bytes_read()
    assert d.read(e, 100) == bytes(100)
    assert bytes_read() - before < 64 * 1024


def test_format_over_budget_is_skipped(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"x" * 100)
    e = Entry(
        "a.txt", str(tmp_path / "a.txt"), "/a.txt", "file", 100, 1, 1, 7, "text/plain"
    )

    class Hungry(Format):
        type = "x/hungry"
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            d.read(e, 100)
            yield Dataset(anchor=e.rel)

    d = directory([e])
    datasets, _ = run_post(d, collect(Hungry()), 5.0, byte_budget=10)
    assert datasets[0].format == ""
    assert any("skipped: reading 100 bytes" in text for _, text in d.warnings)


def test_a_slow_formats_result_is_kept(caplog):
    # The time depends on the load, the result must not (spec recognition,
    # "A slow format's result is kept"): logged, not in the result
    class Slow(Format):
        type = "x/slow"
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            time.sleep(0.05)
            yield Dataset(anchor="/a.txt")

    d = directory([entry("a.txt")])
    datasets, _ = run_post(d, collect(Slow()), slow=0.01, byte_budget=1)
    assert datasets[0].format == "t/slow"
    assert d.warnings == [] and not d.retry
    assert "x/slow" in caplog.text or "t/slow" in caplog.text
    assert "slow: over 0.01 s" in caplog.text


def test_second_directory_anchor_is_rejected():
    # Two formats anchoring at the directory would give two datasets with one
    # anchor, which the index rejects: the directory itself is claimable
    class First(Format):
        type = "x/first"
        priority = 70
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            yield Dataset(anchor=d.rel, members=("/a.txt",))

    class Second(Format):
        type = "x/second"
        priority = 20
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            yield Dataset(anchor=d.rel, members=("/b.txt",))

    d = directory([entry("a.txt"), entry("b.txt")])
    datasets, _ = run_post(d, collect(First(), Second()), 5.0, 1)
    assert [(x.anchor, x.format) for x in datasets] == [
        ("/", "t/first"),
        ("/b.txt", ""),
    ]
    assert ("/", "t/second: / already claimed by t/first") in d.warnings


def test_claim_of_a_file_elsewhere_is_rejected():
    class Reacher(Format):
        type = "x/reach"
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            yield Dataset(anchor="/a.txt", members=("/a.txt", "/elsewhere/b.txt"))

    d = directory([entry("a.txt")])
    datasets, _ = run_post(d, collect(Reacher()), 5.0, 1)
    assert datasets[0].format == ""  # stays a single file
    assert (
        "/a.txt",
        "t/reacher: claim outside / rejected: /elsewhere/b.txt",
    ) in d.warnings


def test_pre_order_dataset_that_does_not_collapse_is_ignored():
    class Eager(Format):
        type = "x/eager"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            yield Dataset(anchor=d.rel, basis="too early")

    d = directory([entry("x", None)], phase="pre")
    assert run_pre(d, collect(Eager()), 5.0, 1) is None
    assert (
        "/",
        "t/eager: ignored a pre-order dataset that doesn't collapse /",
    ) in d.warnings


def test_core_owned_fields_are_reset():
    # parent comes only from adoption and collapsed only from the pre-order call
    class Sneaky(Format):
        type = "x/sneaky"
        reacts_to = frozenset({"text/plain"})

        def recognize(self, d):
            yield Dataset(anchor="/a.txt", parent="/elsewhere", collapsed=True)

    d = directory([entry("a.txt")])
    datasets, _ = run_post(d, collect(Sneaky()), 5.0, 1)
    assert datasets[0].parent is None and datasets[0].collapsed is False
    assert "t/sneaky: parent and collapsed are set by the core" in datasets[0].warnings


def test_crashing_format_does_not_stop_recognition():
    class Crash(Format):
        type = "x/crash"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            raise RuntimeError("boom")

    d = directory([entry("a.txt")])
    datasets, _ = run_post(d, collect(Crash()), 5.0, 1)
    assert [x.anchor for x in datasets] == ["/a.txt"]
    assert any("failed: RuntimeError('boom')" in text for _, text in d.warnings)


def test_pre_order_collapse():
    class Marker(Format):
        type = "x/marked"
        reacts_to = frozenset({DIRECTORY})

        def recognize(self, d):
            if d.phase == "pre" and d.entry("MARKER"):
                yield Dataset(anchor=d.rel, collapsed=True, basis="MARKER present")

    d = directory([entry("MARKER", None)], phase="pre")
    ds = run_pre(d, collect(Marker()), 5.0, 1)
    assert ds.collapsed and ds.type == "x/marked" and ds.members == () and ds.uid == 1
    assert (
        ds.mtime == 0.5
    )  # the directory's own mtime: the contents were not visited (R37)
    assert (
        run_pre(directory([entry("x", None)], phase="pre"), collect(Marker()), 5.0, 1)
        is None
    )


def test_result_json_round_trip():
    result = Result(
        datasets=[
            Dataset(anchor="/b", members=("/b",), type="t/b"),
            Dataset(
                anchor="/a",
                parts=("/b",),
                type="t/a",
                format="x/y",
                basis="z",
                warnings=("w",),
                parent=None,
            ),
        ],
        warnings=[("/b", "hm"), ("/a", "oh")],
    )
    data = result.to_json()
    assert [d["anchor"] for d in data["datasets"]] == ["/a", "/b"]
    assert data["warnings"] == [["/a", "oh"], ["/b", "hm"]]
