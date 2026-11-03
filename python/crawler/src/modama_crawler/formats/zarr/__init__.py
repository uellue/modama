"""Zarr stores (v2 and v3) as single collapsed datasets; a store inside a store belongs to the outer one."""

import json
from collections.abc import Iterable

from .. import DIRECTORY, Collection, Dataset, Directory, Format

V3 = "zarr.json"
V2 = (".zarray", ".zgroup")
READ_LIMIT = 64 * 1024  # zarr.json with large attributes is legal, but not read


class Zarr(Format):
    type = "application/x-zarr"
    priority = 80
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        if d.phase != "pre":
            return
        marker = d.entry(V3)
        if marker is not None and marker.kind == "file":
            # The marker's presence decides the collapse; its content only adds detail
            basis, warnings = f"{V3} present", ()
            if marker.size > READ_LIMIT:
                warnings = (f"{V3} is {marker.size} bytes, too large to inspect",)
            else:
                try:
                    meta = json.loads(d.read(marker, READ_LIMIT))
                    if not isinstance(meta, dict):
                        raise TypeError(f"not a JSON object but {type(meta).__name__}")
                    basis = f"{V3}: zarr_format {meta.get('zarr_format')}, node_type {meta.get('node_type')}"
                except (TypeError, ValueError, UnicodeDecodeError) as e:
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
