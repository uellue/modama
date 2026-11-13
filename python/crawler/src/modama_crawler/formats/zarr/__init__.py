"""Zarr stores (v2 and v3) as single collapsed datasets; a store inside a store belongs to the outer one."""

import json
from collections.abc import Iterable

from .. import DIRECTORY, Collection, Dataset, Directory, Format

V3 = "zarr.json"
V2 = (".zarray", ".zgroup")
READ_LIMIT = 64 * 1024  # zarr.json with large attributes is legal, but not read


class Zarr(Format):
    type = "application/x-zarr"
    display_name = "Zarr"
    priority = 80
    reacts_to = frozenset({DIRECTORY})

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        if d.phase != "pre":
            return
        marker = d.entry(V3)
        if marker is not None and marker.kind == "file":
            # The marker's presence decides the collapse; its content only adds detail
            basis, warnings, meta = f"{V3} present", (), None
            if marker.size > READ_LIMIT:
                warnings = (f"{V3} is {marker.size} bytes, too large to inspect",)
            else:
                try:
                    meta = json.loads(d.read(marker, READ_LIMIT))
                    if not isinstance(meta, dict):
                        raise TypeError(f"not a JSON object but {type(meta).__name__}")
                    basis = f"{V3}: zarr_format {meta.get('zarr_format')}, node_type {meta.get('node_type')}"
                except (TypeError, ValueError, UnicodeDecodeError) as e:
                    meta, warnings = None, (f"{V3} cannot be parsed: {e}",)
            found = Dataset(
                anchor=d.rel, collapsed=True, basis=basis, warnings=warnings
            )
            if (kept := self.described(d, found, meta)) is not None:
                yield kept
            return
        for name in V2:
            marker = d.entry(name)
            if marker is not None and marker.kind == "file":
                found = Dataset(
                    anchor=d.rel, collapsed=True, basis=f"{name} present (Zarr v2)"
                )
                if (kept := self.described(d, found, None)) is not None:
                    yield kept
                return

    def described(
        self, d: Directory, dataset: Dataset, meta: dict | None
    ) -> Dataset | None:
        """The store's dataset as this format gives it, None if the store is not of
        its type; meta is the parsed zarr.json, None for a v2 store or one not read,
        so that a subtype reads it only once (common/zspy; review of
        read-limit-per-file)."""
        return dataset


COLLECTION = Collection("zarr", [Zarr()])
