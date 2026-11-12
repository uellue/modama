"""K2IS acquisitions: a .gtg tag file with its 8 sector files, as one dataset anchored at the .gtg (k2is.xml).

The sector files belong to a .gtg by LiberTEM's naming rule (K2ISDataSet):
`X.gtg` takes `X*.bin`, and an acquisition has exactly 8 (NUM_SECTORS).
Extraction reads the .gtg's tags through RosettaSciIO's DM reader on our own
handle (dm.parsed), keeps all of them but GMS's user-interface settings as
values and describes the capture by the summary line of DM images
(dm.headline); the sector files are not read. A .gtg with its 8 sector files is a
capture whatever it holds (a broken one fails at extraction); only a .gtg
without sector files is checked for a DM header (decisions 172, 183).
"""

from collections.abc import Iterable
from pathlib import Path

from modama_crawler.formats import Collection, Dataset, Directory, Extracted, Format

from ..dm import at, header, headline, kept, parsed, terms, version

HERE = Path(__file__).parent
ACQUISITION = "application/x.k2is"
TAGS = "application/x.dm-gtg"
SECTOR = "application/x.k2is-sector"
SECTORS = 8


class K2is(Format):
    type = ACQUISITION
    display_name = "Gatan K2 IS"
    # Before the formats at 60, which may claim a dropped file (decision 165)
    priority = 61
    reacts_to = frozenset({TAGS, SECTOR})
    # 2: a lone .gtg without a DM header loses the .gtg type (decisions 172, 183)
    version = "2"

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
            # A lone .gtg: of the type with a DM header; a DM3 one is a file of
            # interest (decision 183); one that cannot be read keeps its type
            elif (data := header(d, tags)) is not None:
                match version(data):
                    case 3:
                        d.note(tags, "file of interest: DM3 .gtg, review by hand")
                    case None:
                        d.not_of_type(tags, "no DM header")
        orphans = sorted(s.name for s in sectors if s.rel not in taken)
        if orphans:
            d.warn(
                d.rel,
                f"{len(orphans)} K2IS sector file(s) without a .gtg file of their "
                f"stem, for example {orphans[0]}",
            )

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """Every tag of the .gtg but GMS's user-interface settings as values, the DM summary line (spec formats/k2is, D4)."""
        tags = parsed(root + dataset.anchor).tags_dict
        # The scan shape and the microscope from the root, as LiberTEM reads
        # `.SI Dimensions.Size X` (_get_nav_shape): SI Image Tags holds groups
        # of the same names
        name = at(tags, "Microscope Info.Name")
        subjects = ([name] if isinstance(name, str) else []) + terms(tags)
        # As the DM part's values; a .gtg has no image, so no mapped metadata
        values = {"original_metadata": kept(tags)}
        return Extracted(summary=headline(tags), subjects=subjects, values=values)


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection("em", [K2is()], mime_files=(HERE / "k2is.xml",))
