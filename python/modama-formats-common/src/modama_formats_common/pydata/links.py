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

# Per file, the same on every crawl (decision 342): objects and links listed,
# and bytes read (the real master: 1,125 and 483 KB)
MAX_LISTED = 5000
BUDGET = 4 << 20
# Per folder: fewer HDF5 files have nothing to link to, more are not listed
MIN_FILES, MAX_FILES = 2, 200

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

    {"hdf5": False} if h5py cannot open it; else {"hdf5": True, "external":
    [names], "virtual": [names], "cut": bool}, each name as `matched` gives
    it. Groups are entered by hard links only, objects opened by hard links
    only, at most MAX_LISTED objects and links (a cut is said); links are
    read with `links.get_val`, never followed. The exception classes caught at
    the open are those LiberTEM's HDF5 dataset catches when it detects a file
    (`detect_params`); RuntimeError and SystemError in the listing go to the
    inspection's outcome "failed".
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
        stack = [h5.id]
        while stack and not cut:
            gid = stack.pop()
            found: list[tuple[bytes, int]] = []

            def take(name, info, found=found):
                found.append((name, info.type))

            gid.links.iterate(take, info=True, order=h5py.h5.ITER_NATIVE)
            for name, kind in found:
                count += 1
                if count > MAX_LISTED:
                    cut = True
                    break
                if kind == h5py.h5l.TYPE_EXTERNAL:
                    file = gid.links.get_val(name)[0].decode("utf-8", "replace")
                    if (target := matched(file)) is not None:
                        external.add(target)
                elif kind == h5py.h5l.TYPE_HARD:
                    obj = h5py.h5o.open(gid, name)
                    if isinstance(obj, h5py.h5g.GroupID):
                        stack.append(obj)
                    elif isinstance(obj, h5py.h5d.DatasetID):
                        dcpl = obj.get_create_plist()
                        if dcpl.get_layout() == h5py.h5d.VIRTUAL:
                            for i in range(dcpl.get_virtual_count()):
                                file = dcpl.get_virtual_filename(i)
                                if file != "." and (
                                    target := matched(file, virtual=True)
                                ):
                                    virtual.add(target)
    return {
        "hdf5": True,
        "external": sorted(external),
        "virtual": sorted(virtual),
        "cut": cut,
    }


def grouped(
    names: dict[str, set[str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, str]]:
    """Anchors with their members, the targets two anchors name, and cycles, from what each listed file names.

    `names`: a listed file -> the HDF5 files of the folder it names, its own
    name left out. A back-link is a link from one of a file's targets whose
    only target is that file. An anchor names at least one file, is named by
    no other listed file but through a back-link, and is not one of two
    files each the other's only target (a cycle); its members are its
    targets but those another anchor names too (design D4).
    Returns (anchor -> members, shared target -> anchors, file of a cycle -> the other).
    """
    by: dict[str, set[str]] = {}
    for x, targets in names.items():
        for t in targets:
            by.setdefault(t, set()).add(x)
    cycles = {
        x: next(iter(t))
        for x, t in names.items()
        if len(t) == 1 and names.get(next(iter(t))) == {x}
    }
    anchors = [
        x
        for x, targets in sorted(names.items())
        if targets
        and x not in cycles
        and all(y in targets and names.get(y) == {x} for y in by.get(x, ()))
    ]
    named: dict[str, list[str]] = {}
    for x in anchors:
        for t in names[x]:
            named.setdefault(t, []).append(x)
    shared = {t: sorted(xs) for t, xs in named.items() if len(xs) > 1}
    members = {x: sorted(t for t in names[x] if t not in shared) for x in anchors}
    return {x: m for x, m in members.items() if m}, shared, cycles
