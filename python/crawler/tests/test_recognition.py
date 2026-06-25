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
def test_mib(tmp_path):
    listing = [
        ('0.testmib', 'f', ''),
        ('7.testhdr', 'f', '1.testmib\n0.testmib\n'),
        ('1.testhdr', 'f', 'x.testmib\nb/x.testmib\n'),
        ('a/', 'd', ''),
        ('a/a.txt', 'f', ''),
        ('a/b.txt', 'f', ''),
        ('a/d.txt', 'f', ''),
        ('b/', 'd', ''),
        ('b/a.txt', 'f', ''),
        ('b/b.txt', 'f', ''),
        ('b/d.txt', 'f', ''),
        ('b/x.testmib', 'f', ''),
        ('b/b', 'l', 'b/'),
        ('1.testmib', 'f', ''),
        ('c', 'l', 'a/'),
        ('a.txt', 'f', ''),
        ('b.txt', 'f', ''),
        ('d.txt', 'f', ''),
        ('x.testmib', 'f', ''),
    ]

    for path, kind, content in listing:
        if kind == 'f':
            (tmp_path / Path(path)).write_text(content)
        elif kind == 'd':
            (tmp_path / Path(path)).mkdir(exist_ok=True)
            if content != '':
                raise RuntimeError('WTF')
        elif kind == 'l':
            target_is_directory = content[-1] == '/'
            (tmp_path / Path(path)).symlink_to(content, target_is_directory=target_is_directory)
        else:
            raise RuntimeError('WTF')
    shuffle(listing)
    return (listing, tmp_path)