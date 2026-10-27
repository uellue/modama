"""Zarr stores (v2 and v3) as single collapsed datasets; a store inside a store belongs to the outer one."""

import json
from collections.abc import Iterable

from .. import DIRECTORY, Collection, Dataset, Directory, Format

V3 = "zarr.json"
V2 = (".zarray", ".zgroup")


class Zarr(Format):
    type = "application/x-zarr"
    priority = 80
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        if d.phase != "pre":
            return
        marker = d.entry(V3)
        if marker is not None and marker.kind == "file":
            warnings = ()
            try:
                meta = json.loads(d.read(marker, 64 * 1024))
                basis = f"{V3}: zarr_format {meta.get('zarr_format')}, node_type {meta.get('node_type')}"
            except (ValueError, UnicodeDecodeError) as e:
                basis = f"{V3} present"
                warnings = (f"{V3} cannot be parsed: {e}",)
            yield Dataset(anchor=d.rel, collapsed=True, basis=basis, warnings=warnings)
            return
        for name in V2:
            marker = d.entry(name)
            if marker is not None and marker.kind == "file":
                yield Dataset(
                    anchor=d.rel, collapsed=True, basis=f"{name} present (Zarr v2)"
                )
                return


COLLECTION = Collection("zarr", [Zarr()])
