from pathlib import Path
import re
from urllib.parse import unquote_plus
from datetime import datetime
from dataclasses import dataclass
import os


# from mgmtinterface import quote_path
def quote_path(path: str) -> str:
    """
    Consistently quote the path such that it can appear in the
    query part of a URL, as close to the standard as possible
    (https://url.spec.whatwg.org/)
    """


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
            raise ValueError(f'Path {path} contains ".", .." path elements.')

    # Sanitize path (II): Append to directory root, make absolute
    # (don't resolve to not follow symlinks) and make sure it is relative to the
    # root
    path = (root / path).absolute().relative_to(root, walk_up=False)
    return path


@dataclass
class RepositoryConfig:
    """Configuration for the OAI-PMH repository."""

    admin_email: str
    base_url: str
    repository_name: str
    earliest_datestamp: datetime  # Changed from timestamp to datetime
    granularity: str
    compression: list
    batch_size: int = 10
    data_root: Path = Path("/storage/er-c-data")

    @classmethod
    def from_env(cls, base_url_optional: bool = True) -> "RepositoryConfig":
        """Create config from environment variables.

        Args:
            base_url_optional: If True, base_url defaults to empty string if not set.
                             If False, raises ValueError when BASE_URL is missing.
        """
        admin_email = os.environ.get("OAI_ADMIN_EMAIL", "admin@example.org")
        base_url = os.environ.get("OAI_BASE_URL", "" if base_url_optional else None)

        if not base_url and not base_url_optional:
            raise ValueError(
                "OAI_BASE_URL environment variable is required but not set"
            )

        # Get optional repository parameters with defaults
        repository_name = os.environ.get("OAI_REPOSITORY_NAME", "Modama OAI-PMH server")
        earliest_datestamp_str = os.environ.get(
            "OAI_EARLIEST_DATESTAMP", "1970-01-01T00:00:00Z"
        )

        # Parse earliest datestamp
        from datetime import datetime as dt_type

        try:
            earliest_datestamp = dt_type.fromisoformat(
                earliest_datestamp_str.replace("Z", "+00:00")
            )
        except ValueError:
            earliest_datestamp = dt_type.fromtimestamp(0)  # fallback to epoch

        granularity = os.environ.get("OAI_GRANULARITY", "YYYY-MM-DDThh:mm:ssZ")
        compression_str = os.environ.get("OAI_COMPRESSION", "identity")
        compression = [c.strip() for c in compression_str.split(",") if c.strip()]
        batch_size = int(os.environ.get("BATCH_SIZE", 10))

        data_root_str = os.environ.get("MODAMA_DATA_ROOT", "/storage/er-c-data")
        data_root = Path(data_root_str)

        return cls(
            admin_email=admin_email,
            base_url=base_url or "",
            repository_name=repository_name,
            earliest_datestamp=earliest_datestamp,
            granularity=granularity,
            compression=compression,
            batch_size=batch_size,
            data_root=data_root,
        )
