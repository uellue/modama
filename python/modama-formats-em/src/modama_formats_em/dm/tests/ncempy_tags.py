"""Every tag of a DM3/DM4 file as ncempy reads it (`fileDM.allTags`), one `name = value` per line, sorted.

Read-only: opens the file for reading and prints. For comparing with what the crawler's DM extractor keeps: a
second reader, when the first one's output looks wrong (test_extract.py's CAMERA tags were taken from its output).
ncempy is not a dependency of this package; run it where ncempy is installed (`uv pip install ncempy`).

    python ncempy_tags.py FILE > OUT.txt
"""

import sys

from ncempy.io import dm

with dm.fileDM(sys.argv[1], on_memory=False) as f:
    tags = f.allTags
for name in sorted(tags):
    value = tags[name]
    text = repr(value) if not isinstance(value, str) else value
    print(f"{name} = {text[:300]}")
print(f"# {len(tags)} tags", file=sys.stderr)
