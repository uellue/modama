"""Directories that are one dataset as a whole and whose contents are not worth indexing.

Each format recognises its kind from the directory's listing alone, in the
pre-order call, so nothing below it is visited (architecture A, R11).
"""

from collections.abc import Iterable

from .. import DIRECTORY, Collection, Dataset, Directory, Format


class Collapse(Format):
    priority = 90
    reacts_to = frozenset({DIRECTORY})

    def basis(self, d: Directory) -> str | None:
        """Why this directory is of this kind, or None."""
        raise NotImplementedError

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        if d.phase != "pre":
            return
        basis = self.basis(d)
        if basis:
            yield Dataset(anchor=d.rel, collapsed=True, basis=basis)


class Venv(Collapse):
    type = "application/x.python-venv"
    display_name = "Python virtual environment"

    def basis(self, d):
        return "contains pyvenv.cfg" if d.entry("pyvenv.cfg") else None


class Conda(Collapse):
    type = "application/x.conda-env"
    display_name = "Conda environment"

    def basis(self, d):
        e = d.entry("conda-meta")
        return "contains conda-meta/" if e and e.kind == "dir" else None


class NamedDirectory(Collapse):
    """A directory recognised by its own name."""

    directory_name = ""

    def basis(self, d):
        return (
            f"directory is named {self.directory_name}"
            if d.name == self.directory_name
            else None
        )


class NodeModules(NamedDirectory):
    type = "application/x.node-modules"
    display_name = "Node.js modules"
    directory_name = "node_modules"


class Git(NamedDirectory):
    type = "application/x.git"
    display_name = "Git repository"
    directory_name = ".git"


class Pycache(NamedDirectory):
    type = "application/x.python-cache"
    display_name = "Python bytecode cache"
    directory_name = "__pycache__"


class IpynbCheckpoints(NamedDirectory):
    type = "application/x.ipynb-checkpoints"
    display_name = "Jupyter notebook checkpoints"
    directory_name = ".ipynb_checkpoints"


COLLECTION = Collection(
    "collapse", [Venv(), Conda(), NodeModules(), Git(), Pycache(), IpynbCheckpoints()]
)
