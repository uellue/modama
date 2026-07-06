import os
from pathlib import Path
from typing import Callable, Sequence, Any
import bisect
import functools
from collections import OrderedDict
import warnings

import natsort


from .recognition import FileHandler, guess


CrawlResultItem = FileHandler


default_key = natsort.natsort_keygen()


def is_real_dir(p: Path) -> bool:
    return not p.is_symlink() and p.is_dir()


def sanitize(root: Path, path: Path) -> Path:
    # Sanitize path elements
    for p in path.parts:
        if p in ('.', '..'):
            raise ValueError(f'Path {path} contains "., .." path elements.')

    # Sanitize path (II): Append to directory root, make absolute
    # (don't resolve to not follow symlinks) and make sure it is relative to the
    # root
    path = (root / path).absolute().relative_to(root, walk_up=False)
    return path


def remove_smaller_equal(outstanding: OrderedDict[Path, Any], item: Path, outer_key: Callable):
    keys = list(outstanding.keys())
    keys.sort(key=outer_key)

    idx = bisect.bisect_right(
        a=keys,
        x=outer_key(item),
        key=outer_key
    )
    for extra_key in keys[:idx]:
        outstanding.pop(extra_key)
        if extra_key != item:
            warnings.warn(f"Walked beyond outstanding item {extra_key} to {item} without encountering it")


def _time_in_range(time: float, since: float | None, until: float | None) -> bool:
    if since is not None and time < since:
        return False
    if until is not None and time > until:
        return False
    return True


def matches_oai_pmh_datestamp_limits(
        stat: os.stat_result | Any,
        *,
        c_since: float | None = None,
        c_until: float | None = None,
        m_since: float | None = None,
        m_until: float | None = None,
) -> bool:
    """Return True if the stat matches OAI-PMH selective harvesting time bounds.

    Per OAI-PMH selective harvesting, a record is included if its modification
    timestamp or its creation timestamp falls within the inclusive [from, until]
    range. If no time bounds are specified, all records match.
    """
    m_active = (m_since is not None) or (m_until is not None)
    c_active = (c_since is not None) or (c_until is not None)

    if not m_active and not c_active:
        return True

    m_matches = _time_in_range(stat.st_mtime, m_since, m_until) if m_active else False
    c_matches = _time_in_range(stat.st_ctime, c_since, c_until) if c_active else False
    return m_matches or c_matches


def _nextpath_inner(
        root: Path, continuation: tuple,
        stable_key: Callable, outer_key: Callable, n: int,
        outstanding: OrderedDict[Path, Any]) -> tuple[Sequence[Path], bool]:
    # Find file entries that come after the continuation token in the chosen
    # sort order. If the continuation token is a directory, it descends into
    # that directory. It will list files until it encounters a directory so that
    # the filtering and sorting does not have to be repeated for folders
    # containing many files. The last entry of the result can be used as a
    # continuation token to continue. If there's nothing more to find, an empty
    # list is returned.

    # Don't modify the argument since the calling function
    # will need to keep track of outstanding bits itself
    outstanding = outstanding.copy()

    def process(contents, root, base, outstanding, n):
        result = []
        cont = False
        # TODO limit oversize since files a and z on top level may span the entire repository
        while contents and (len(result) < n or outstanding):
            # print(result, n, outstanding)
            sn = contents.pop(0)
            result.append(base / sn)
            remove_smaller_equal(
                outstanding=outstanding,
                item=base / sn,
                outer_key=outer_key
            )
            item = root / base / sn
            # We found a directory and need to descend now to keep
            # the stable order.
            # Descending is delegated to outer function which calls
            # this function with an appropriate continuation key
            if is_real_dir(item):
                cont = True
                break

        return result, (len(contents) > 0 or cont)

    # We ascend from the depth of the continuation token up
    # until we can match it with existing directories
    # and find sth to return
    for i in range(len(continuation)):
        subpath = Path(*continuation[:len(continuation)-i])
        # The continuation token was an existing directory and our next task is
        # to descend into that directory. No need to filter since the
        # directory content comes after the containing directory in the sort
        # order
        cont = root / subpath
        if is_real_dir(cont) and i == 0:
            target_dir = cont
            # TODO limit recursion depth
            # print(target_dir, os.listdir(target_dir))
            contents = sorted((x for x in os.listdir(target_dir)), key=stable_key)
            if contents:
                return process(
                    contents=contents,
                    root=root,
                    base=subpath,
                    outstanding=outstanding,
                    n=n,
                )
        # It is a file or doesn't exist
        else:
            # Look at contents one level up
            containing_dir = cont.parent
            # We list the containing dir
            if is_real_dir(containing_dir):
                contents = sorted(
                    (x for x in os.listdir(containing_dir)),
                    key=stable_key)
                # We filter out everything smaller or equal to the matching
                # level of our continuation token
                comp_item = stable_key(continuation[len(continuation)-i-1])

                idx = bisect.bisect(
                    a=contents,
                    x=comp_item,
                    key=stable_key
                )
                contents = contents[idx:]
                if contents:
                    return process(
                        contents=contents,
                        root=root,
                        base=subpath.parent,
                        outstanding=outstanding,
                        n=n,
                    )
    # Apparently we didn't find anything
    return ([], False)


def stringify(item):
    if isinstance(item, int):
        return f"{item:020d}"
    elif isinstance(item, float):
        return f"{item:040.20f}"
    else:
        return str(item)


def _mk_stable(key):
    def stable_key(item):
        # natsort does not guarantee a stable sorting order since e.g.
        # "023", "0023", "23", "0023" all map to the same key "('', 23)". By
        # appending the item itself, we guarantee a stable order for
        # unique items. Since we are working with strings resp. byte sequences,
        # a stable order should be establishable one way or another.

        # stringify() because otherwise e.g. natsort may return different types
        # for the items, leading to invalid comparisons.
        return tuple(stringify(k) for k in key(item)) + (str(item), )
    return stable_key


def outer_key(item, key):
    # The key is applied separately at each level of the path hierarchy.
    # For that reason we create a nested key with a tuple of tuples
    # that should resolve to the same sort order
    parts = Path(item).parts
    return tuple(key(p) for p in parts)


def crawl(
            root: Path | str, continuation: Path | str,
            key: Callable = default_key, n: int = 1,
            c_since: float | None = None, c_until: float | None = None,
            m_since: float | None = None, m_until: float | None = None) -> tuple[dict[Path, CrawlResultItem], Path | None]:
    # _nextpath_inner() stops returning entries when it encounters a directory
    # since it will need to descend. That's why this outer function keeps
    # calling _nextpath_inner() until our bucket is full
    result = {}
    outstanding = OrderedDict()
    seen = set()
    claimed = OrderedDict()
    root = Path(root).resolve(strict=True)
    continuation = Path(continuation)

    continuation = sanitize(root=root, path=continuation)

    stable_key = _mk_stable(key)

    outer = functools.partial(outer_key, key=stable_key)

    def dict_item_key(item):
        return outer(item[0])

    continuation_parts = continuation.parts
    if not continuation_parts:
        # This will resolve to the root node in _nextpath_inner.
        continuation_parts = ('', )
    new_continuation = continuation
    # TODO limit oversize since files a and z on top level may span the entire repository
    finished = False
    while len(result) < n or len(outstanding) != 0:
        missing = n-len(result)
        pieces, cont = _nextpath_inner(
            root=root, continuation=continuation_parts,
            stable_key=stable_key,
            outer_key=outer,
            n=missing,
            outstanding=outstanding,
        )
        # The inner function would have found more, we ar enot done
        if cont is True:
            finished = False
        # The inner function hit an end point and didn't return enough items.
        # This will only persist if the while loop condition
        # is not met anymore in the next pass
        if cont is False and len(pieces) < missing:
            finished = True
        # This one will stick since we exit the loop here
        if len(pieces) == 0:
            finished = True
            break
        for piece in pieces:
            seen.add(piece)
            new_continuation = piece
            ignore = piece in outstanding
            remove_smaller_equal(
                outstanding=outstanding,
                item=piece,
                outer_key=outer,
            )
            stat = (root / piece).stat(follow_symlinks=False)
            ignore = ignore or not matches_oai_pmh_datestamp_limits(
                stat,
                c_since=c_since,
                c_until=c_until,
                m_since=m_since,
                m_until=m_until,
            )
            if ignore:
                continue
            guesses = guess(root / piece)
            handler = FileHandler.create(root, piece, guesses)
            for member in handler.members:
                # Must have been the other handler's path attribute to end up there
                if member in claimed:
                    # SHOULD be identical to handler if we just encountered another
                    # file. However, that should have been in outstanding and ignored
                    other_handler = claimed[member]
                    warnings.warn(
                        "Encountered existing handler "
                        f"{handler.path} that claims {member} without appearing in outstanding files"
                    )
                    if set(other_handler.members) != set(handler.members):
                        warnings.warn(
                            "Encountered member file mismatch between "
                            f"{handler.path} {handler.members} and {other_handler.path} {other_handler.members}."
                        )
                    if type(other_handler) is not type(handler):
                        warnings.warn(
                            "Encountered type mismatch between "
                            f"{handler.path} {type(handler)} and {other_handler.path} {type(other_handler)}."
                        )
                # Handle secondary files that will be ignored in listing See if
                # we need to put this in the "outstanding" list only if this
                # member comes after the continuation token. Otherwise out of
                # scope, safely ignored. If the member is the current item, we don't add
                # to outstanding files since we are handling it just now.
                elif member != piece and outer(member) > outer(continuation):
                    # Truly looking forward beyond current place in tree
                    if outer(member) > outer(piece):
                        outstanding[member] = handler
                    elif member not in seen:
                        warnings.warn(
                            f"Member {member} of {handler.path} encountered that wasn't seen "
                            "before, but should have been seen."
                        )
                if outer(member) <= outer(continuation):
                    warnings.warn(
                            f"Member {member} of {handler.path} encountered that comes before "
                            f"continuation token {continuation}."
                        )
                claimed[member] = handler
            # Don't overwrite previously added handler
            # We've already warned in case of a duplicate
            if handler.path not in result:
                result[handler.path] = handler
        continuation_parts = Path(pieces[-1]).parts
    result = OrderedDict(sorted(result.items(), key=dict_item_key))
    if outstanding:
        raise Exception(str(outstanding))
    if n == 0:
        # No files processed, return input continuation
        pass
    elif finished:
        # Finished processing all files
        new_continuation = None
    # else: keep new_continuation as the last file processed
    return (result, new_continuation)
