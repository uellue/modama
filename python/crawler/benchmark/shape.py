"""The shape of a test tree, from a listing of the real one: a sample of its directories
with their files' sizes, times and name patterns, without the real names.

Input: the survey's listing (`find -printf '%y\\t%s\\t%T@\\t%p\\n'`, gzipped TSV:
type, size, mtime, path). Output: a gzipped TSV for `generate.py`, one line per
directory (`d`, path, mtime) or file (`f`, path, mtime, size), parents first.

Each directory of the listing is taken with the probability FRACTION, with all its
files; its parents come along as directories without their files. Names are replaced:
directories by `d<n>`, file names by a prefix per directory and pattern, keeping a
trailing number's digits (frame series stay series) and the extension (globs still
match). Names the formats react to (`NAMES`) are kept, as is the `.save` and `.zarr`
suffix of a directory. Symlinks are left out (the crawler skips them).

    python3 shape.py LISTING.tsv.gz FRACTION SEED > SHAPE.tsv.gz
"""

import gzip
import random
import re
import sys
from collections import defaultdict

# The names the crawler's formats look for (collapse, zarr)
NAMES = {
    ".git", ".ipynb_checkpoints", "__pycache__", "node_modules", "conda-meta",
    "site-packages", "pyvenv.cfg", ".zarray", ".zgroup", ".zattrs", "zarr.json",
}  # fmt: skip
DIR_SUFFIXES = (".save", ".zarr")
NUMBERED = re.compile(r"^(.*?)(\d+)$")
SUFFIXES = re.compile(r"(\.[A-Za-z][A-Za-z0-9_-]{0,7}){1,2}$")


def split_name(name):
    """(stem, extension): up to two trailing suffixes that look like extensions (a
    letter, then up to seven letters, digits, `_` or `-`), so that `a.tar.gz` keeps
    `.tar.gz`; anything else, such as parameters written into a name, is stem."""
    m = SUFFIXES.search(name)
    return (name[: m.start()], m.group()) if m and m.start() > 0 else (name, "")


def main(listing, fraction, seed):
    rng = random.Random(seed)
    dirs, files = {}, defaultdict(list)
    with gzip.open(listing, "rt", encoding="utf-8", errors="surrogateescape") as f:
        for line in f:
            kind, size, mtime, path = line.rstrip("\n").split("\t", 3)
            if kind == "d":
                dirs[path] = mtime
            elif kind == "f":
                parent, _, name = path.rpartition("/")
                files[parent].append((name, size, mtime))
    root = min(dirs, key=len)
    taken = {d for d in sorted(dirs) if d != root and rng.random() < fraction}

    names = {root: "."}

    def new_path(d):
        if d not in names:
            parent, _, name = d.rpartition("/")
            above = new_path(parent)  # first, so that numbers go down the tree
            if name in NAMES:
                new = name
            else:
                suffix = next((s for s in DIR_SUFFIXES if name.endswith(s)), "")
                new = f"d{len(names)}{suffix}"
            names[d] = above + "/" + new
        return names[d]

    out = []
    for d in sorted(taken):
        new_path(d)
    for d in sorted(names, key=lambda d: names[d]):
        if d == root:
            continue
        out.append(f"d\t{names[d]}\t{dirs[d]}")
        if d not in taken:
            continue
        prefixes = {}
        for name, size, mtime in files[d]:
            if name in NAMES:
                new = name
            else:
                stem, ext = split_name(name)
                m = NUMBERED.match(stem)
                head, digits = (m.group(1), m.group(2)) if m else (stem, "")
                p = prefixes.setdefault((head, len(digits), ext), f"f{len(prefixes)}")
                new = f"{p}_{digits or len(prefixes)}{ext}"
                # Two names that differ only in what was replaced
                while new in prefixes:
                    new = "x" + new
                prefixes[new] = new
            out.append(f"f\t{names[d]}/{new}\t{mtime}\t{size}")
    with gzip.open(sys.stdout.buffer, "wt", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    nfiles = sum(1 for line in out if line[0] == "f")
    total = sum(int(line.rsplit("\t", 1)[1]) for line in out if line[0] == "f")
    print(
        f"{len(out) - nfiles} directories, {nfiles} files, "
        f"{total / 1e12:.1f} TB apparent size (sparse)",
        file=sys.stderr,
    )


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(sys.argv[1], float(sys.argv[2]), int(sys.argv[3]))
