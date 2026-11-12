"""K2IS acquisitions: a .gtg tag file with its 8 sector files, as one dataset anchored at the .gtg (k2is.xml).

The sector files belong to a .gtg by LiberTEM's naming rule (K2ISDataSet):
`X.gtg` takes `X*.bin`, and an acquisition has exactly 8 (NUM_SECTORS).
Extraction reads the .gtg's tags through RosettaSciIO's DM reader on our own
handle (dm.parsed) and describes all of them but GMS's user-interface
settings; the sector files are not read. A .gtg with its 8 sector files is a
capture whatever it holds (a broken one fails at extraction); only a .gtg
without sector files is checked for the DM4 header (decision 172).
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from ..dm import HEADER, parsed, tag_paths, version

HERE = Path(__file__).parent
ACQUISITION = "application/x.k2is"
TAGS = "application/x.dm-gtg"
SECTOR = "application/x.k2is-sector"
SECTORS = 8
# First in the description: the tags LiberTEM reads for the scan shape
# (_get_nav_shape), and the microscope's
FIRST = ("SI Dimensions", "Microscope Info")
# GMS's user-interface settings, left out of the description (decision 129, D4):
# - a tag group of the image viewer's class: the window's and the screen's
#   relative position, zoom, auto zoom, view name, viewer class, its version
VIEWER_CLASSES = frozenset({"cm_stdviewerimagedisplayer"})
# - the group Items of Session Info: the definition of GMS's Session Info form
#   (per field its label, tag path, data type, precision, units and default
#   value); the fields' values are in Session Info itself and stay
FORM = ("Session Info", "Items")


class K2is(Format):
    type = ACQUISITION
    display_name = "Gatan K2 IS"
    # Before em/dm3 (60): a lone .gtg without the DM4 header may be DM3 (decision 165)
    priority = 61
    reacts_to = frozenset({TAGS, SECTOR})
    # 2: a lone .gtg without the DM4 header loses the .gtg type (decision 172)
    version = "2"
    # 2: every tag but the user-interface settings (decision 129), not rounded
    extractor_version = "3"

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        sectors = d.of_type(SECTOR)
        taken = set()
        # The longest stem first: a sector file belongs to the longest stem it
        # starts with, whether that stem has 8 or not, so that an incomplete
        # scan_2_.gtg does not take sectors from a complete scan_.gtg (D3)
        for tags in sorted(d.of_type(TAGS), key=lambda e: -len(e.name)):
            stem = tags.name[: -len(".gtg")]
            mine = [
                s.rel
                for s in sectors
                if s.rel not in taken
                and s.name.startswith(stem)
                # In any case, as the .gtg glob (D3)
                and s.name.lower().endswith(".bin")
            ]
            taken.update(mine)
            if len(mine) == SECTORS:
                yield Dataset(
                    anchor=tags.rel,
                    members=(tags.rel, *mine),
                    basis=f"{SECTORS} sector files {stem}*.bin",
                )
            elif mine:
                d.warn(
                    tags.rel,
                    f"{tags.name}: {len(mine)} sector files {stem}*.bin, "
                    f"a K2IS acquisition has {SECTORS}",
                )
            elif version(d.read(tags, HEADER)) != 4:
                # A lone .gtg: of the type only with the DM4 header (decision 147)
                d.not_of_type(tags, "no DM4 header")
        orphans = sorted(s.name for s in sectors if s.rel not in taken)
        if orphans:
            d.warn(
                d.rel,
                f"{len(orphans)} K2IS sector file(s) without a .gtg file of their "
                f"stem, for example {orphans[0]}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Every tag of the .gtg but GMS's user-interface settings, as the reader gives them (spec formats/k2is, D4)."""
        tags = parsed(root + dataset.anchor).tags_dict
        # At the root, as LiberTEM reads `.SI Dimensions.Size X` (_get_nav_shape):
        # SI Image Tags holds groups of the same names
        values = {
            group: tags[group]
            for group in FIRST
            if isinstance(tags.get(group), dict) and tags[group]
        }
        # The scan shape and the microscope first, then the rest in the reader's order
        ordered = {**values, **{k: v for k, v in tags.items() if k not in values}}
        summary = [f"{path} {value}" for path, value in tag_paths(ordered, _settings)]
        subjects = (
            [n]
            if isinstance(n := values.get("Microscope Info", {}).get("Name"), str)
            else []
        )
        return Extracted(summary=summary, subjects=subjects, values=values)


def _settings(path: tuple[str, ...], group: dict) -> bool:
    """A tag group of GMS's user-interface settings, left out of the description."""
    return group.get("Class Name") in VIEWER_CLASSES or path[-2:] == FORM


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [K2is()], mime_files=(HERE / "k2is.xml",))
