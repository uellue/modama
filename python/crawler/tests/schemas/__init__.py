"""OAI-PMH Dublin Core schema definitions and download utilities."""

import requests
from pathlib import Path


# Schema URLs for OAI-PMH and Dublin Core
SCHEMAS = {
    "OAI-PMH.xsd": "http://www.openarchives.org/OAI/2.0/OAI-PMH.xsd",
    "oai_dc.xsd": "http://www.openarchives.org/OAI/2.0/oai_dc.xsd",
    "simpledc20021212.xsd": "http://dublincore.org/schemas/xmls/simpledc20021212.xsd",
}


def download_schema(url: str, filename: str) -> Path:
    """Download a schema file from the given URL.

    Args:
        url: The URL to download the schema from
        filename: The filename to save as

    Returns:
        Path to the downloaded file
    """
    schemas_dir = Path(__file__).parent
    schema_path = schemas_dir / filename

    response = requests.get(url, timeout=30)
    response.raise_for_status()

    with open(schema_path, "wb") as f:
        f.write(response.content)

    return schema_path


def get_schema_path(schema_name: str) -> Path:
    """Get the path to a downloaded schema file.

    Args:
        schema_name: The name of the schema (key from SCHEMAS dict)

    Returns:
        Path to the schema file, or raises FileNotFoundError if not found
    """
    schemas_dir = Path(__file__).parent
    schema_path = schemas_dir / schema_name

    if not schema_path.exists():
        raise FileNotFoundError(
            f"Schema '{schema_name}' not found. Run download_all_schemas() first."
        )

    return schema_path


def download_all_schemas() -> dict[str, Path]:
    """Download all schemas defined in SCHEMAS.

    Returns:
        Dictionary mapping schema names to their downloaded paths
    """
    schemas_dir = Path(__file__).parent

    # Create schemas directory if it doesn't exist
    schemas_dir.mkdir(parents=True, exist_ok=True)

    downloaded = {}
    for name, url in SCHEMAS.items():
        try:
            path = download_schema(url, name)
            downloaded[name] = path
            print(f"Downloaded {name} to {path}")
        except requests.RequestException as e:
            print(f"Failed to download {name}: {e}")

    return downloaded


if __name__ == "__main__":
    # Download all schemas when run as script
    download_all_schemas()
