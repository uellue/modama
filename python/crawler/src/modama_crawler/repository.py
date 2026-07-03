import pathlib

from urllib.parse import quote_plus


# from mgmtinterface import quote_path
def quote_path(path: str):
    """
    Consistently quote the path such that it can appear in the
    query part of a URL, as close to the standard as possible
    (https://url.spec.whatwg.org/)
    """
    return quote_plus(path, safe="!$'()*,/:;?@")


def get_identifier(path: pathlib.Path, root: pathlib.Path) -> str:
    # abspath = root / path
    # st = abspath.stat()
    # identifier = {
    #     'path': str(path),
    #     'size': st.st_size,
    # }
    # suffix = json.dumps(identifier).encode().hex().lower()
    return f"https://er-c-data-mgmt.fz-juelich.de/browse?path={quote_path('/' + str(path))}"


# FIXME get from environment
def get_publisher() -> str:
    return "ER-C"
