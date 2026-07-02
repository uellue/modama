import os
import pathlib
from typing import Callable, Sequence, Any
import bisect
import functools
from collections import OrderedDict
import warnings

import natsort


from .recognition import FileHandler, guess


# FIXME define rich type with metadata and whatnot
CrawlResultItem = FileHandler


default_key = natsort.natsort_keygen()


def is_real_dir(p: pathlib.Path) -> bool:
    return not p.is_symlink() and p.is_dir()


def remove_smaller_equal(outstanding: OrderedDict[pathlib.Path, Any], item: pathlib.Path, outer_key: Callable):
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


def _nextpath_inner(
        root: pathlib.Path, continuation: tuple,
        deterministic_key: Callable, outer_key: Callable, n: int,
        outstanding: OrderedDict[pathlib.Path, Any]) -> Sequence[pathlib.Path]:
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

    # Don't modify the argument since the calling function
    # will need to keep track of outstanding bits itself
    outstanding = outstanding.copy()

    def process(contents, root, base, outstanding, n):
        result = []
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
            # the deterministic order.
            # Descending is delegated to outer function which calls
            # this function with an appropriate continuation key
            if is_real_dir(item):
                break
        return result

    for i in range(len(continuation)):
        subpath = pathlib.Path(*continuation[:len(continuation)-i])
        # The continuation token was an existing directory and our next task is
        # to descend into that directory for things. No need to filter since the
        # directory content comes after the containing directory in the sort
        # order
        cont = root / subpath
        if is_real_dir(cont) and i == 0:
            target_dir = cont
            # TODO limit recursion depth
            contents = sorted((x for x in os.listdir(target_dir)), key=deterministic_key)
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
                    return process(
                        contents=contents,
                        root=root,
                        base=subpath.parent,
                        outstanding=outstanding,
                        n=n,
                    )
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
            key: Callable = default_key, n: int = 1) -> tuple[dict[pathlib.Path, CrawlResultItem], pathlib.Path]:
    # _nextpath_inner() stops returning entries when it encounters a directory
    # since it will need to descend. That's why this outer function keeps
    # calling _nextpath_inner() until our bucket is full
    result = {}
    outstanding = OrderedDict()
    seen = set()
    claimed = OrderedDict()
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

    def dict_item_key(item):
        return outer(item[0])

    continuation_parts = continuation.parts
    if not continuation_parts:
        # This will resolve to the root node in _nextpath_inner.
        continuation_parts = ('', )
    new_continuation = continuation
    # TODO limit oversize since files a and z on top level may span the entire repository
    while len(result) < n or len(outstanding) != 0:
        pieces = _nextpath_inner(
            root=root, continuation=continuation_parts,
            deterministic_key=deterministic_key,
            outer_key=outer,
            n=n-len(result),
            outstanding=outstanding,
        )
        if len(pieces) == 0:
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
        continuation_parts = pathlib.Path(pieces[-1]).parts
    result = OrderedDict(sorted(result.items(), key=dict_item_key))
    if outstanding:
        raise Exception(str(outstanding))
    return (result, new_continuation)
