import os
import pathlib
from typing import Callable, Sequence
import bisect
import functools

import natsort


from .recognition import FileHandler, guess


# FIXME define rich type with metadata and whatnot
CrawlResultItem = FileHandler


default_key = natsort.natsort_keygen()


def is_real_dir(p: pathlib.Path) -> bool:
    return not p.is_symlink() and p.is_dir()


def _nextpath_inner(
        root: pathlib.Path, continuation: tuple,
        deterministic_key: Callable, n: int) -> Sequence[pathlib.Path]:
    # Find file entries that come after the continuation token in the chosen
    # sort order. If the continuation token is a directory, it descends into
    # that directory. It will list files until it encounters a directory so that
    # the filtering and sorting does not have to be repeated for folders
    # containing many files. The last entry of the result can be used as a
    # continuation token to continue. If there's nothing more to find, an empty
    # list is returned. deterministic_key()

    # we descend from the depth of the continuation token up
    # until we can match it with existing directories
    # and find sth to return
    for i in range(len(continuation)):
        subpath = pathlib.Path(*continuation[:len(continuation)-i])
        # The continuation token was an existing directory and our next task is
        # to descend into that directory for things. No need to filter since the
        # directory content comes after the containing directory in the sort
        # order
        cont = root / subpath
        if is_real_dir(cont) and i == 0:
            target_dir = cont
            contents = sorted((x for x in os.listdir(target_dir)), key=deterministic_key)
            if contents:
                result = []
                base = subpath
                while contents and len(result) < n:
                    sn = contents.pop(0)
                    result.append(base / sn)
                    item = root / base / sn
                    # We found a directory and need to descend now to keep
                    # the deterministic order.
                    # Descending is delegated to outer function which calls
                    # this function with an appropriate continuation key
                    if is_real_dir(item):
                        break
                return result
        # It is a file or doesn't exist
        else:
            # Look at contents one level up
            containing_dir = cont.parent
            # We list the containing dir
            if is_real_dir(containing_dir):
                contents = sorted(
                    (x for x in os.listdir(containing_dir)),
                    key=deterministic_key)
                # We filter out everything smaller or equal to the matching
                # level of our continuation token
                comp_item = deterministic_key(continuation[len(continuation)-i-1])

                idx = bisect.bisect(
                    a=contents,
                    x=comp_item,
                    key=deterministic_key
                )
                contents = contents[idx:]
                if contents:
                    result = []
                    base = subpath.parent
                    while contents and len(result) < n:
                        sn = contents.pop(0)
                        result.append(base / sn)
                        # We found a directory and need to descend now to keep
                        # the deterministic order.
                        # Descending is delegated to outer function which calls
                        # this function with an appropriate continuation key
                        if is_real_dir(root / base / sn):
                            break
                    return result
    # Apparently we didn't find anything
    return []


def _mk_deterministic(key):
    def deterministic_key(item):
        # natsort does not guarantee a deterministic sorting order since e.g.
        # "023", "0023", "23", "0023" all map to the same key "('', 23)". By
        # appending the item itself, we guarantee a well-defined order for
        # unique items. Since we are working with strings resp. byte sequences,
        # a deterministic order should be establishable one way or another.
        return tuple(key(item)) + (item, )
    return deterministic_key


def outer_key(item, key):
    # The key is applied separately at each level of the path hierarchy.
    # For that reason we create a nested key with a tuple of tuples
    # that should resolve to the same sort order
    parts = pathlib.Path(item).parts
    return tuple(key(p) for p in parts)


def crawl(
            root: pathlib.Path | str, continuation: pathlib.Path | str,
            key: Callable = default_key, n: int = 1) -> dict[pathlib.Path, CrawlResultItem]:
    # _nextpath_inner() stops returning entries when it encounters a directory
    # since it will need to descend. That's why this outer function keeps
    # calling _nextpath_inner() until our bucket is full
    result = {}
    outstanding = {}
    root = pathlib.Path(root).resolve(strict=True)
    continuation = pathlib.Path(continuation)

    # Sanitize continuation token
    for p in continuation.parts:
        if p in ('.', '..'):
            raise ValueError(f'Continuation token {continuation} contains "., .." path elements.')

    # Sanitize continuation token (II): Append to directory root, make absolute
    # (don't resolve to not follow symlinks) and make sure it is relative to the
    # root
    continuation = (root / continuation).absolute().relative_to(root, walk_up=False)

    deterministic_key = _mk_deterministic(key)

    outer = functools.partial(outer_key, key=deterministic_key)

    continuation_parts = continuation.parts
    if not continuation_parts:
        # This will resolve to the root node in _nextpath_inner.
        continuation_parts = ('', )
    while len(result) < n or len(outstanding) != 0:
        pieces = _nextpath_inner(
            root=root, continuation=continuation_parts,
            deterministic_key=deterministic_key, n=n-len(result)
        )
        if len(pieces) == 0:
            break
        for piece in pieces:
            if piece in outstanding:
                outstanding.pop(piece)
                continue
            guesses = guess(root / piece)
            handler = FileHandler.create(root, piece, guesses)
            for member in handler.members:
                if member == piece:
                    continue
                elif member in result:
                    raise Exception()
                    result.pop(member)
                else:
                    raise Exception()
                    outstanding[member] = handler
            result[piece] = handler
        continuation_parts = pathlib.Path(pieces[-1]).parts
    return result
