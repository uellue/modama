"""K2IS acquisitions: a .gtg tag file with its 8 sector files, as one dataset anchored at the .gtg (k2is.xml).

The sector files belong to a .gtg by LiberTEM's naming rule (K2ISDataSet):
`X.gtg` takes `X*.bin`, and an acquisition has exactly 8 (NUM_SECTORS).
Extraction reads the .gtg's tags through RosettaSciIO's DM reader on our own
handle (dm.parsed); the sector files are not read.
"""

from collections.abc import Iterable, Iterator
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from ..dm import parsed

HERE = Path(__file__).parent
ACQUISITION = "application/x.k2is"
TAGS = "application/x.dm-gtg"
SECTOR = "application/x.k2is-sector"
SECTORS = 8
# The tags LiberTEM reads for the scan shape (_get_nav_shape), and the microscope's
SHOWN = ("SI Dimensions", "Microscope Info")


class K2is(Format):
    type = ACQUISITION
    display_name = "Gatan K2 IS"
    priority = 60
    reacts_to = frozenset({TAGS, SECTOR})
    extractor_version = "1"

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        sectors = d.of_type(SECTOR)
        claimed = set()
        # The longest stem first, so that X_1.gtg keeps its sectors from X_.gtg
        for tags in sorted(d.of_type(TAGS), key=lambda e: -len(e.name)):
            stem = tags.name[: -len(".gtg")]
            mine = [
                s.rel
                for s in sectors
                if s.rel not in claimed
                and s.name.startswith(stem)
                and s.name.endswith(".bin")
            ]
            if len(mine) != SECTORS:
                continue
            claimed.update(mine)
            yield Dataset(
                anchor=tags.rel,
                members=(tags.rel, *mine),
                basis=f"{SECTORS} sector files {stem}*.bin",
            )
        orphans = sorted(s.name for s in sectors if s.rel not in claimed)
        if orphans:
            d.warn(
                d.rel,
                f"{len(orphans)} K2IS sector file(s) without a .gtg file and its "
                f"{SECTORS} sectors, for example {orphans[0]}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The .gtg's scan shape and microscope tags, as the reader gives them (spec formats/k2is)."""
        tags = parsed(root + dataset.anchor).tags_dict
        values = {group: found for group in SHOWN if (found := _group(tags, group))}
        summary = [
            f"{group}.{name} {_shown(value)}"
            for group, found in values.items()
            for name, value in found.items()
            if not isinstance(value, dict)
        ]
        subjects = (
            [n]
            if isinstance(n := values.get("Microscope Info", {}).get("Name"), str)
            else []
        )
        return Extracted(summary=summary, subjects=subjects, values=values)


def _group(tags: dict, name: str) -> dict | None:
    """The first tag group of that name, depth first, as the reader gives it."""
    for key, value in _groups(tags):
        if key == name:
            return value
    return None


def _groups(tags: dict) -> Iterator[tuple[str, dict]]:
    for key, value in tags.items():
        if isinstance(value, dict):
            yield key, value
            yield from _groups(value)


def _shown(value) -> str:
    return f"{value:g}" if isinstance(value, float) else str(value)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [K2is()], mime_files=(HERE / "k2is.xml",))
