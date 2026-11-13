"""HDF5 files that link HDF5 files of their folder (change hdf5-links; spec formats/pydata).

- `runs`: links that count up, one entry instead of hundreds (design D2).
- `matched`: the name a target file is matched by in the folder, or None for
  one never looked up (design D3).
- `listed`: run by recognition in a worker process (`Directory.inspect`) on
  an `.h5` file: the names its external links and virtual-dataset sources
  are matched by, bounded by counts (design D5). Nothing is ever followed.
- `grouped`: anchors and members from what each listed file names (design D4).

A target name is only ever compared with the folder's names, never joined
into a path that is opened.
"""

import re
from collections.abc import Iterable

# Per file, the same on every crawl (decision 342): objects and links listed (the
# real master: 1,125); the bytes read are bounded by Hdf5Links.read_limit
MAX_LISTED = 5000
# Per folder: fewer HDF5 files have nothing to link to, more are not listed
MIN_FILES, MAX_FILES = 2, 200
# The names of HDF5 files among the files an earlier format claimed, whose types
# are not offered: the globs of the HDF5 types (pydata.xml) and Velox's .emd
NAMES = (".h5", ".hdf5", ".hdf", ".nxs", ".hspy", ".emd")

DIGITS = re.compile(r"(\d+)")


def _next(a: str, b: str) -> bool:
    """Whether b is a with one run of decimal digits, at the same place and of the same width, one more."""
    x, y = DIGITS.split(a), DIGITS.split(b)
    if len(x) != len(y):
        return False
    differ = [i for i, (p, q) in enumerate(zip(x, y, strict=True)) if p != q]
    if len(differ) != 1:
        return False
    i = differ[0]
    return i % 2 == 1 and len(x[i]) == len(y[i]) and int(y[i]) == int(x[i]) + 1


def runs(items: Iterable[tuple[str, str, str]]) -> list[list]:
    """(name, file, path) of a group's links as runs [first name, last name, first file, last file, path, count].

    Sorted by the names' bytes, not in stored order (a dense group stores its
    links in the order of their names' hashes); next to each other, with the
    same path, each name and file the previous one's plus one in one run of
    digits of the same width (`d9`, `d10` are no run).
    """
    out: list[list] = []
    for name, file, path in sorted(items, key=lambda t: t[0].encode()):
        last = out[-1] if out else None
        if (
            last is not None
            and last[4] == path
            and _next(last[1], name)
            and _next(last[3], file)
        ):
            last[1], last[3] = name, file
            last[5] += 1
        else:
            out.append([name, name, file, file, path, 1])
    return out


def source_runs(items: Iterable[tuple[str, str]]) -> list[list[str]]:
    """A virtual dataset's (file, path) mappings in mapping order, consecutive files counting up as one `[first … last, path]`."""
    out: list[list] = []
    for file, path in items:
        last = out[-1] if out else None
        if last is not None and last[2] == path and _next(last[1], file):
            last[1] = file
        else:
            out.append([file, file, path])
    return [[f if f == g else f"{f} … {g}", p] for f, g, p in out]


def entry(first: str, last: str) -> str:
    """The run's own part of a key: `data_000001 … data_000441`, or one name."""
    return first if first == last else f"{first} … {last}"


def matched(file: str, virtual: bool = False) -> str | None:
    """The name a target file is matched by in the folder; None if it is never looked up.

    A bare name as it is (a Windows path too: HDF5 on Linux takes it as one
    name); an absolute path by its last part, as HDF5 looks for it beside the
    linking file when the absolute path does not exist (decision 341); a
    relative path with a folder part (`./x.h5` too) and a printf-style source
    name of a virtual dataset (`%b`) never.
    """
    if virtual and "%" in file:
        return None
    if file.startswith("/"):
        name = file.rsplit("/", 1)[1]
    elif "/" in file:
        return None
    else:
        name = file
    return None if name in ("", ".", "..") else name


def listed(f) -> dict:
    """In a worker: what an HDF5 file's external links and virtual-dataset sources name.

    {"hdf5": False} if h5py cannot open it; {"hdf5": True, "error": text} if
    the library fails while listing (a broken checksum, a link storage it
    cannot iterate): the same file gives the same error, a result for that
    state of the file, not tried again (code review of hdf5-links, S1);
    else {"hdf5": True, "external": [names], "virtual": [names], "cut":
    bool}, each name as `matched` gives it. Groups are entered by hard links
    only, objects opened by hard links only, at most MAX_LISTED objects and
    links, counted as HDF5 hands them over and the iteration stopped there,
    so that one group of 100,000 links is not read whole (S2; a cut is
    said); links are read with `links.get_val`, never followed. The
    exception classes are those LiberTEM's HDF5 dataset catches when it
    detects a file (`detect_params`): at the open (OSError, KeyError,
    ValueError, TypeError), in the walk (RuntimeError, SystemError), with
    KeyError, ValueError and OSError, as h5py raises them for broken
    metadata. A read error is still told apart: the inspection's file object
    notes it, whatever is caught here.
    """
    import h5py

    try:
        h5 = h5py.File(f, "r", locking=False)
    except (OSError, KeyError, ValueError, TypeError):
        return {"hdf5": False}
    external: set[str] = set()
    virtual: set[str] = set()
    count = 0
    cut = False
    with h5:
        try:
            stack = [h5.id]
            while stack and not cut:
                gid = stack.pop()
                found: list[tuple[bytes, int]] = []

                def take(name, info, found=found):
                    nonlocal count, cut
                    count += 1
                    if count > MAX_LISTED:
                        cut = True
                        return True  # ends the iteration (H5Literate)
                    found.append((name, info.type))
                    return None

                library(gid.links.iterate, take, info=True, order=h5py.h5.ITER_NATIVE)
                for name, kind in found:
                    if kind == h5py.h5l.TYPE_EXTERNAL:
                        file = library(gid.links.get_val, name)[0]
                        target = matched(file.decode("utf-8", "replace"))
                        if target is not None:
                            external.add(target)
                    elif kind == h5py.h5l.TYPE_HARD:
                        obj = library(h5py.h5o.open, gid, name)
                        if isinstance(obj, h5py.h5g.GroupID):
                            stack.append(obj)
                        elif isinstance(obj, h5py.h5d.DatasetID):
                            virtual |= sources(obj)
        except LibraryError as e:
            return {"hdf5": True, "error": str(e)}
    return {
        "hdf5": True,
        "external": sorted(external),
        "virtual": sorted(virtual),
        "cut": cut,
    }


def sources(dataset) -> set[str]:
    """The names a virtual dataset's mappings onto other files are matched by (a
    h5py DatasetID; nothing for any other layout), from its creation property list."""
    import h5py

    dcpl = library(dataset.get_create_plist)
    if library(dcpl.get_layout) != h5py.h5d.VIRTUAL:
        return set()
    found = set()
    for i in range(library(dcpl.get_virtual_count)):
        file = library(dcpl.get_virtual_filename, i)
        if file != "." and (target := matched(file, virtual=True)):
            found.add(target)
    return found


class LibraryError(Exception):
    """h5py's own error while listing: the same file gives the same error."""


def library(call, *args, **kwargs):
    """call(*args, **kwargs), one of h5py's, its errors as LibraryError: only the
    library's errors are a final result, not ours (second code review, nit). The
    classes are those LiberTEM's HDF5 dataset catches while it walks a file."""
    try:
        return call(*args, **kwargs)
    except (RuntimeError, SystemError, KeyError, ValueError, OSError) as e:
        raise LibraryError(f"{type(e).__name__}: {e}") from e


def grouped(
    names: dict[str, set[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[str]]]:
    """Anchors with their members, the targets two candidates name, and the files that
    name others but cannot anchor, from what each listed file names (design D4).

    `names`: a listed file -> the HDF5 files of the folder it names, its own
    name left out. A back-link from y to x is a link from one of x's targets
    whose only target is x, while x names more than y (a data file that links
    its master; two files each the other's only target are no such pair). A
    candidate names at least one file and is named by no other listed file
    but through a back-link; its members are its targets but those another
    candidate names too; an anchor is a candidate with members. A file that
    names others, is no candidate and no anchor's member (a ring of any
    length, a chain's middle) is blocked by the files that name it.
    Returns (anchor -> members, shared target -> its candidates, blocked file -> its namers).
    """
    by: dict[str, set[str]] = {}
    for x, targets in names.items():
        for t in targets:
            by.setdefault(t, set()).add(x)

    def back(y: str, x: str) -> bool:
        return y in names[x] and names.get(y) == {x} and names[x] != {y}

    candidates = [
        x
        for x, targets in sorted(names.items())
        if targets and all(back(y, x) for y in by.get(x, ()))
    ]
    named: dict[str, list[str]] = {}
    for x in candidates:
        for t in names[x]:
            named.setdefault(t, []).append(x)
    shared = {t: sorted(xs) for t, xs in named.items() if len(xs) > 1}
    members = {x: sorted(t for t in names[x] if t not in shared) for x in candidates}
    anchors = {x: m for x, m in members.items() if m}
    in_dataset = {m for ms in anchors.values() for m in ms}
    blocked = {
        x: sorted(y for y in by.get(x, ()) if not back(y, x))
        for x, targets in sorted(names.items())
        if targets and x not in candidates and x not in in_dataset
    }
    return anchors, shared, blocked
