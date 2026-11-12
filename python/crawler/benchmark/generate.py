"""Builds a test tree from a shape (`shape.py`): directories, and files as sparse files
of the listed size (holes, no data written, so they take almost no space), with the
listed modification times. Python 3.6 or newer, standard library only, so that it
runs on a storage server.

Writes only below TARGET, which must not exist yet or be empty; never deletes or
overwrites anything.

    python3 generate.py SHAPE.tsv.gz TARGET
"""

import gzip
import os
import sys


def main(shape, target):
    if os.path.exists(target) and os.listdir(target):
        sys.exit(f"{target} is not empty; give a new or empty directory")
    os.makedirs(target, exist_ok=True)
    dirs, nfiles = [], 0
    with gzip.open(shape, "rt", encoding="utf-8") as f:
        for line in f:
            fields = line.rstrip("\n").split("\t")
            path = os.path.join(target, fields[1])
            if fields[0] == "d":
                os.mkdir(path)
                dirs.append((path, float(fields[2])))
            else:
                # "x": fails instead of overwriting; truncate makes a hole of the size
                with open(path, "xb") as out:
                    out.truncate(int(fields[3]))
                mtime = float(fields[2])
                os.utime(path, (mtime, mtime))
                nfiles += 1
    # Directory times last: creating their entries changed them
    for path, mtime in reversed(dirs):
        os.utime(path, (mtime, mtime))
    print(f"{len(dirs)} directories, {nfiles} files in {target}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
