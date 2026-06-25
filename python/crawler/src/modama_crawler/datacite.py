import pathlib
import json
import copy


def get_identifier(path: pathlib.Path, root: pathlib.Path):
    abspath = root / path
    st = abspath.stat()
    identifier = {
        'path': str(path),
        'size': st.st_size,
    }
    suffix = json.dumps(identifier).encode().hex().lower()
    return f"10.88888/{suffix}"


# FIXME get from environment
def get_publisher():
    return "ER-C"


def merge_datacite(records):
    '''
    Merge datacite records in descending priority.

    Extend properties that allow multiple entries, and
    set properties with a single value if they haven't been set yet.
    '''
    # Via https://datacite-metadata-schema.readthedocs.io/_/downloads/en/4.7/pdf/
    sequence_keys = (
        "creators", "titles", "subjects", "contributors", "dates",
        "alternateIdentifiers", "relatedIdentifiers", "sizes",
        "formats", "rightsList", "descriptions", "geoLocations",
        "fundingReferences", "relatedItems",
    )
    result = {}
    for r in records:
        for key, value in r.items():
            if key in sequence_keys:
                if key not in result:
                    result[key] = []
                for item in value:
                    if item not in result[key]:
                        result[key].append(copy.deepcopy(item))
            else:
                if key not in result:
                    result[key] = copy.deepcopy(value)
    return result
