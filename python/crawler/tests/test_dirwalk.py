import functools
from random import shuffle
from pathlib import Path
import bisect
from types import SimpleNamespace

import pytest

from modama_crawler.dirwalk import (
    crawl,
    default_key,
    matches_oai_pmh_datestamp_limits,
    outer_key,
    _mk_stable,
)


reference_key = functools.partial(outer_key, key=_mk_stable(default_key))


@pytest.fixture
def test_dir(tmp_path):
    listing = [
        ('a/', 'd'),
        ('a/a.txt', 'f'),
        ('a/b.txt', 'f'),
        ('a/d.txt', 'f'),
        ('b/', 'd'),
        ('b/a.txt', 'f'),
        ('b/b.txt', 'f'),
        ('b/d.txt', 'f'),
        ('b/b', 'l'),
        ('c', 'l'),
        ('a.txt', 'f'),
        ('b.txt', 'f'),
        ('d.txt', 'f'),
    ]

    for path, kind in listing:
        if kind == 'f':
            (tmp_path / Path(path)).touch(exist_ok=True)
        elif kind == 'd':
            (tmp_path / Path(path)).mkdir(exist_ok=True)
        elif kind == 'l' and path == 'c':
            (tmp_path / Path(path)).symlink_to('a', target_is_directory=True)
        elif kind == 'l' and path == 'b/b':
            (tmp_path / Path(path)).symlink_to('b', target_is_directory=True)
        else:
            raise RuntimeError('WTF')
    shuffle(listing)
    return (listing, tmp_path)


def test_walk(test_dir):
    listing, tmp_path = test_dir
    shuffle(listing)

    res, continuation = crawl(
        root=tmp_path,
        continuation='',
        n=len(listing)
    )
    print(res, continuation)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)
    # When all items are processed, continuation should be None (finished)
    assert continuation is None
    assert list(res.keys()) == files


@pytest.mark.parametrize(
    'n', tuple(range(20)) + (100, )
)
def test_walk_count(test_dir, n):
    listing, tmp_path = test_dir
    shuffle(listing)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)
    res, continuation = crawl(
        root=tmp_path,
        continuation='',
        n=n
    )
    print(res, continuation)
    expected = files[:n]
    assert list(res.keys()) == expected
    # When n >= total files, crawling is finished, continuation should be None
    # When n < total files and we got some files, there are more items, continuation should not be None
    # When n=0, we got 0 files from root, continuation should be the input continuation ('')
    if n >= len(files):
        assert continuation is None
    elif n == 0:
        # When n=0, we didn't process any files, so continuation should be the input
        assert continuation == Path('')
    else:
        assert continuation is not None
        # continuation should be the last file in the result
        assert continuation == expected[-1]


@pytest.mark.parametrize(
    'count', (0, 1, 2, 5, 1000)
)
def test_walk_skip(test_dir, count):
    listing, tmp_path = test_dir
    shuffle(listing)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)

    for n in range(len(files)):
        res, continuation = crawl(
            root=tmp_path,
            continuation=files[n],
            n=count,
        )
        # We skip one at n=0
        remaining = len(files) - n - 1
        print(n, remaining, res, continuation)
        expected = files[n+1:n+1+count]
        assert list(res.keys()) == expected
        if count == 0:
            # When count=0, we didn't process any files, so continuation should
            # be the input
            assert continuation == files[n]
        # We must recognize that we are past the end
        elif count > remaining:
            print(count, remaining)
            assert continuation is None
        # We must recognize that there's more to fetch
        elif count < remaining:
            print(count, remaining)
            assert continuation is not None
            assert continuation == expected[-1]
        # The behavior for count == remaining is undefined since we may either
        # realize that the listing is exhausted, or finish "on the mark"
        # without realizing that there wouldn't be a next one.
        else:
            assert continuation in (None, expected[-1])


def test_matches_oai_pmh_datestamp_limits():
    stat = SimpleNamespace(st_mtime=10.0, st_ctime=20.0)

    assert matches_oai_pmh_datestamp_limits(stat)
    assert matches_oai_pmh_datestamp_limits(stat, m_since=1.0, m_until=10.0)
    assert matches_oai_pmh_datestamp_limits(stat, c_since=20.0, c_until=30.0)
    assert matches_oai_pmh_datestamp_limits(stat, m_since=11.0, c_since=19.0)
    assert matches_oai_pmh_datestamp_limits(stat, m_until=11.0, c_until=20.0)

    assert not matches_oai_pmh_datestamp_limits(stat, m_since=11.0, m_until=12.0)
    assert not matches_oai_pmh_datestamp_limits(stat, c_since=21.0, c_until=22.0)
    assert not matches_oai_pmh_datestamp_limits(stat, m_since=11.0, c_since=21.0)


@pytest.mark.parametrize(
    'continuation', ('0', '', None, 'ab', 'c', 'c/a.txt', 'XXX')
)
def test_walk_noexist(test_dir, continuation):
    listing, tmp_path = test_dir
    shuffle(listing)

    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)
    continuation = 'ab'
    index = bisect.bisect(
        a=files,
        x=reference_key(continuation),
        key=reference_key,
    )

    res, continuation = crawl(
        root=tmp_path,
        continuation=continuation,
        n=1000
    )
    print(res, continuation)
    expected = files[index:]
    assert list(res.keys()) == expected
    # With n=1000, we should get all remaining files, so continuation should be None (finished)
    assert continuation is None


@pytest.mark.parametrize(
    'continuation', ('0', '', 'ab', 'c', 'c/a.txt', 'XXX')
)
def test_walk_stupidkey(test_dir, continuation):
    listing, tmp_path = test_dir
    shuffle(listing)

    def stupid_key(item):
        # reverse
        return str(item)[::-1]

    my_key = _mk_stable(stupid_key)

    my_reference_key = functools.partial(outer_key, key=my_key)

    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=my_reference_key)

    index = bisect.bisect(
        a=files,
        x=my_reference_key(continuation),
        key=my_reference_key,
    )

    res, continuation = crawl(
        root=tmp_path,
        continuation=continuation,
        n=1000,
        key=stupid_key
    )
    print(res, continuation)
    expected = files[index:]
    assert list(res.keys()) == expected
    # With n=1000, we should get all remaining files, so continuation should be None (finished)
    assert continuation is None
