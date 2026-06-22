import pytest

import functools
from random import shuffle
from pathlib import Path
import bisect

from modama_crawler.dirwalk import crawl, default_key, _mk_deterministic


def reference_key(item, key=default_key):
    # The key is applied separately at each level of the path hierarchy.
    # For that reason we create a nested key with a tuple of tuples
    # that should resolve to the same sort order
    parts = Path(item).parts
    return tuple(key(p) for p in parts)


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

    res = crawl(
        root=tmp_path,
        continuation='',
        n=len(listing)
    )
    print(res)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)
    assert res == files


@pytest.mark.parametrize(
    'n', tuple(range(5)) + (100, )
)
def test_walk_count(test_dir, n):
    listing, tmp_path = test_dir
    shuffle(listing)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)
    res = crawl(
        root=tmp_path,
        continuation='',
        n=n
    )
    print(res)
    assert res == files[:n]


@pytest.mark.parametrize(
    'count', (0, 1, 2, 5, 1000)
)
def test_walk_skip(test_dir, count):
    listing, tmp_path = test_dir
    shuffle(listing)
    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=reference_key)

    for n in range(len(files)):
        res = crawl(
            root=tmp_path,
            continuation=files[n],
            n=count,
        )
        print(res)
        assert res == files[n+1:n+1+count]


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

    res = crawl(
        root=tmp_path,
        continuation=continuation,
        n=1000
    )
    print(res)
    assert res == files[index:]


@pytest.mark.parametrize(
    'continuation', ('0', '', None, 'ab', 'c', 'c/a.txt', 'XXX')
)
def test_walk_stupidkey(test_dir, continuation):
    listing, tmp_path = test_dir
    shuffle(listing)

    def stupid_key(item):
        # reverse
        return str(item)[::-1]

    my_key = _mk_deterministic(stupid_key)

    my_reference_key = functools.partial(reference_key, key=my_key)

    files = sorted([Path(f) for f in list(zip(*listing))[0]], key=my_reference_key)
    continuation = 'ab'
    index = bisect.bisect(
        a=files,
        x=my_reference_key(continuation),
        key=my_reference_key,
    )

    res = crawl(
        root=tmp_path,
        continuation=continuation,
        n=1000,
        key=stupid_key
    )
    print(res)
    assert res == files[index:]