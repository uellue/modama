from pathlib import Path
import re
from urllib.parse import unquote_plus, quote_plus


# from mgmtinterface import quote_path
def quote_path(path: str) -> str:
    """
    Consistently quote the path such that it can appear in the
    query part of a URL, as close to the standard as possible
    (https://url.spec.whatwg.org/)
    """
    return quote_plus(path, safe="!$'()*,/:;?@")


def unquote_path(quoted_path: str) -> str:
    return unquote_plus(quoted_path)


def get_identifier(path: Path | None) -> str | None:
    if path is None:
        return None
    else:
        return f"https://er-c-data-mgmt.fz-juelich.de/browse?path={quote_path('/' + str(path))}"


def path_from_identifier(identifier: str) -> str:
    """Extract the path from an OAI-PMH identifier URL.

    This is the inverse of get_identifier().
    """
    # The identifier is a URL like:
    # https://er-c-data-mgmt.fz-juelich.de/browse?path=/some/path
    # Extract the path query parameter
    match = re.search(r"path=([^&]+)", identifier)
    if match:
        path_str = unquote_path(match.group(1))
        # Remove leading slash if present
        if path_str.startswith("/"):
            path_str = path_str[1:]
        return path_str
    raise ValueError(f"Could not extract path from identifier: {identifier}")


# FIXME get from environment
def get_publisher() -> str:
    return "ER-C"


def sanitize(root: Path, path: Path) -> Path:
    # Sanitize path elements
    for p in path.parts:
        if p in (".", ".."):
            raise ValueError(f'Path {path} contains "., .." path elements.')

    # Sanitize path (II): Append to directory root, make absolute
    # (don't resolve to not follow symlinks) and make sure it is relative to the
    # root
    path = (root / path).absolute().relative_to(root, walk_up=False)
    return path
