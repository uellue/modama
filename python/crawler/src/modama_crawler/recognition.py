from __future__ import annotations

import pathlib
from typing import ClassVar, Dict, Sequence, Type, Iterable, Optional
import datetime
from functools import cache
import os
import glob
import tempfile
import inspect

import psycopg
from psycopg.rows import dict_row, tuple_row

from xdg import Mime
import magika
import datacite.schema45
import defusedxml.ElementTree as ET

from .repository import get_identifier, get_publisher


mgk = magika.Magika()


def _get_mime_types_from_db(
    conn: psycopg.Connection, path: pathlib.Path
) -> Sequence[Mime.MIMEtype]:
    """Query MIME types for a path from the database.

    Args:
        conn: Database connection
        path: Absolute path to query (as stored in database)

    Returns:
        List of MIME types, or empty list if path not found
    """
    cur = conn.cursor(row_factory=tuple_row)
    cur.execute(
        """
        SELECT m.mime FROM mimes m
        JOIN datasets d ON m.dataset_id = d.dataset_id
        JOIN files f ON d.path_id = f.path_id
        WHERE f.path = %s
        ORDER BY m.mime
        """,
        (str(path),),
    )
    rows = cur.fetchall()
    if not rows:
        return []

    result = []
    for (mime_str,) in rows:
        try:
            # Parse MIME type string (format: "type/subtype")
            if "/" in mime_str:
                media, subtype = mime_str.split("/", 1)
                # Validate that subtype is not empty
                if not subtype:
                    raise ValueError(
                        f"Invalid MIME type '{mime_str}': subtype is empty"
                    )
                result.append(Mime.MIMEtype(media, subtype))
            else:
                # Single-part MIME types are also invalid for our purposes
                raise ValueError(
                    f"Invalid MIME type '{mime_str}': missing subtype separator"
                )
        except Exception as e:
            # Re-raise as RuntimeError with more context
            raise RuntimeError(
                f"Invalid MIME type in database for path {path}: '{mime_str}'"
            ) from e
    return result


def _get_dataset_members_from_db(
    conn: psycopg.Connection, dataset_path: str
) -> Sequence[pathlib.Path]:
    """Get all member paths for a dataset from the database.

    Args:
        conn: Database connection
        dataset_path: Absolute path of the dataset (as stored in database)

    Returns:
        List of absolute member paths
    """
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(
        """
        SELECT f.path FROM files_in_datasets fid
        JOIN files f ON fid.path_id = f.path_id
        JOIN datasets d ON fid.dataset_id = d.dataset_id
        WHERE f.path = %s
        """,
        (dataset_path,),
    )
    rows = cur.fetchall()
    # Return paths as-is (they are absolute paths from database)
    return [pathlib.Path(row["path"]) for row in rows]


def _get_dataset_mtime_from_db(conn: psycopg.Connection, dataset_path: str) -> float:
    """Get the maximum mtime of all files in a dataset from the database.

    Args:
        conn: Database connection
        dataset_path: Absolute path of the dataset (as stored in database)

    Returns:
        mtime as floating point Unix timestamp
    """
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(
        """
        SELECT MAX(f.mtime) AS mtime FROM files f
        JOIN datasets d ON f.path_id = d.path_id
        WHERE f.path = %s
        UNION ALL
        SELECT MAX(f.mtime) FROM files_in_datasets fid
        JOIN files f ON fid.path_id = f.path_id
        JOIN datasets d ON fid.dataset_id = d.dataset_id
        WHERE f.path = %s
        """,
        (str(dataset_path), str(dataset_path)),
    )
    rows = cur.fetchall()
    return max(row["mtime"] for row in rows if row["mtime"] is not None)


def get_oldest_mtime_from_db(conn: psycopg.Connection, dataset_path: str) -> float:
    """Get the minimum mtime of all files from the database.

    Args:
        conn: Database connection

    Returns:
        mtime as floating point Unix timestamp
    """
    cur = conn.cursor(row_factory=dict_row)
    cur.execute(
        """
        SELECT MIN(f.mtime) AS mtime FROM files
        """
    )
    rows = cur.fetchall()
    return min(row["mtime"] for row in rows)


class DatasetConsistencyError(RuntimeError):
    pass


def guess(path: pathlib.Path) -> Sequence[Mime.MIMEtype]:
    result = []
    res = Mime.get_type2(path, follow=False)
    if res is not None:
        result.append(res)
    mgk_res = mgk.identify_path(path)
    if mgk_res.status is magika.Status.OK:
        result.append(Mime.MIMEtype(mgk_res.output.mime_type))
    return result


class FileHandler:
    _registry: ClassVar[Dict[Mime.MIMEtype, list[Type["FileHandler"]]]] = {}

    file_types: ClassVar[tuple[Mime.MIMEtype, ...]] = (Mime.MIMEtype("", ""),)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.file_types:
            for file_type in cls.file_types:
                cls._registry.setdefault(file_type, []).append(cls)

    def __init__(
        self,
        root: pathlib.Path,
        path: pathlib.Path,
        guesses: Sequence[Mime.MIMEtype],
        conn: psycopg.Connection,
    ):
        self.root = root
        self.path = path
        self.guesses = guesses
        self.conn = conn
        self.abspath = self.root / self.path
        self.members = self._find_all_members()

    def _rebase(self, path):
        self.path = path
        self.abspath = self.root / path

    @classmethod
    def handlers_for_type(
        cls, file_type: Mime.MIMEtype
    ) -> Sequence[Type["FileHandler"]]:
        return tuple(cls._registry.get(file_type, []))

    @classmethod
    def handlers(cls) -> Sequence[Type["FileHandler"]]:
        result = set()
        for handlers in cls._registry.values():
            result.update(handlers)
        return tuple(result)

    @classmethod
    def resolve(
        cls,
        root: pathlib.Path,
        path: pathlib.Path,
        guesses: Sequence[Mime.MIMEtype],
        conn: Optional[psycopg.Connection] = None,
    ) -> Type["FileHandler"]:
        path = pathlib.Path(path)
        root = pathlib.Path(root)

        # If database connection is provided, try to get MIME types from database
        # Use absolute path (root / path) since root is now the filesystem root
        if conn is not None:
            abs_path = root / path
            db_guesses = _get_mime_types_from_db(conn, abs_path)
            if db_guesses:
                guesses = db_guesses
        else:
            raise ValueError("No database connection")

        best_match: Type["FileHandler"] | None = None
        best_priority = -1

        for file_type in guesses:
            for handler_cls in cls.handlers_for_type(file_type):
                priority = handler_cls.matches(root, path, guesses)
                if priority is None:
                    continue
                if not 0 <= priority <= 100:
                    raise ValueError(
                        f"Handler {handler_cls.__name__}.matches() returned invalid priority {priority}; must be 0..100"
                    )
                if priority > best_priority:
                    best_priority = priority
                    best_match = handler_cls

        # If no match found, fall back to octet-stream
        if best_match is None:
            return OctetStream

        return best_match

    @classmethod
    def create(
        cls,
        root: pathlib.Path,
        path: pathlib.Path,
        guesses: Sequence[Mime.MIMEtype],
        conn: psycopg.Connection,
    ) -> "FileHandler":
        handler_cls = cls.resolve(root, path, guesses, conn)
        return handler_cls(root, path, guesses, conn)

    @classmethod
    def matches(
        cls, root: pathlib.Path, path: pathlib.Path, guesses: Sequence[Mime.MIMEtype]
    ) -> int | None:
        """Return 0..100 if this handler can handle the path, otherwise None."""
        if (root / path).exists():
            return 0
        else:
            return None

    @classmethod
    def install_mime_info(cls, application: str | None = None):
        if application is None:
            application = "modama-crawler"
        snippets = []
        handlers = cls.handlers()
        for handler in handlers:
            mimeinfo = handler.xdg_mimeinfo()
            if mimeinfo:
                snippets.append(mimeinfo)
        if snippets:
            filename = application + ".xml"
            header = """<?xml version="1.0"?>
<mime-info xmlns='http://www.freedesktop.org/standards/shared-mime-info'>
"""
            footer = "</mime-info>"
            with tempfile.TemporaryDirectory() as d:
                package_file = os.path.join(d, filename)
                with open(package_file, "w") as f:
                    f.write(header)
                    for snippet in snippets:
                        f.write(snippet)
                        f.write("\n")
                    f.write(footer)
                Mime.install_mime_info(
                    application=application, package_file=package_file
                )

    def _find_all_members(self) -> Iterable[pathlib.Path]:
        # If database connection is available, query for dataset members
        if self.conn is not None:
            # self.path is relative, self.root is absolute
            abs_path = self.root / self.path
            return _get_dataset_members_from_db(self.conn, str(abs_path))
        else:
            raise RuntimeError("No database connection")

    @property
    @cache
    def stat(self):
        return self.abspath.stat()

    def get_mimes(self) -> Sequence[Mime.MIMEtype]:
        return list(self.file_types) + list(self.guesses)

    def get_creators(self):
        try:
            res = self.abspath.owner()
        except KeyError:
            res = str(self.stat.st_uid)
        return [res]

    def get_titles(self):
        return [
            str(self.path),
        ]

    def get_year(self):
        return str(datetime.datetime.fromtimestamp(self.stat.st_ctime).year)

    def get_dates(self) -> Sequence[float]:
        return [self.mtime]

    def get_descriptions(self):
        return [", ".join(f"'{str(m.relative_to(self.root))}'" for m in self.members)]

    @property
    @cache
    def mtime(self) -> float:
        mtime = self.stat.st_mtime
        for member in self.members:
            abspath = self.root / member
            mtime = max(mtime, abspath.stat().st_mtime)
        return mtime

    @property
    @cache
    def db_mtime(self):
        return _get_dataset_mtime_from_db(conn=self.conn, dataset_path=self.abspath)

    @classmethod
    def source_mtime(cls) -> float:
        # Unix timestamp, safe to assume nothing here is older
        result = 0.0
        # A bit questionable, but let's assume only the files containing the
        # ancestry influence the result...
        for parent in cls.__mro__:
            try:
                file = inspect.getfile(parent)
                mtime = os.stat(file).st_mtime
                result = max(result, mtime)
            # Couldn't get source, e.g. builtin
            except TypeError, FileNotFoundError, PermissionError:
                continue
        return result

    @classmethod
    @cache
    def youngest_source_mtime(cls) -> float:
        classes = set()
        for classlist in cls._registry.values():
            classes.update(classlist)
        # print(classes)
        # for c in classes:
        #     print(c, c.source_mtime())
        return max(c.source_mtime() for c in classes)

    @classmethod
    @cache
    def oldest_source_mtime(cls) -> float:
        classes = set()
        for classlist in cls._registry.values():
            classes.update(classlist)
        # print(classes)
        # for c in classes:
        #     print(c, c.source_mtime())
        return min(c.source_mtime() for c in classes)

    def get_resource_type(self):
        g = self.get_mimes()[0]
        return {
            "resourceTypeGeneral": g.media,
            "resourceType": g.subtype,
        }

    def get_formats(self) -> list[str]:
        result = []
        for g in self.get_mimes():
            str_g = str(g)
            # Validate that this is a proper MIME type with subtype
            if not str_g or "/" not in str_g:
                raise ValueError(
                    f"Invalid MIME type from handler: '{str_g}'. "
                    f"MIME types must have format 'type/subtype'. "
                    f"Handler class: {self.__class__.__name__}, File: {self.path}"
                )
            if str_g not in result:
                result.append(str_g)
        # Only keep 'application/octet-stream' if there is no other option
        if len(result) > 1:
            try:
                result.remove("application/octet-stream")
            except ValueError:
                pass
        return result

    def datacite(self):
        raise NotImplementedError
        # FIXME adapt to changes to better suit `oaipmh` module
        record = {
            "identifier": get_identifier(self.path, self.root),
            "creators": self.get_creators(),
            "titles": self.get_titles(),
            "publisher": {"name": get_publisher()},
            "publicationYear": self.get_year(),
            "dates": self.get_dates(),
            "types": self.get_resource_type(),
            "formats": self.get_formats(),
            "schemaVersion": "http://datacite.org/schema/kernel-4",
        }
        datacite.schema45.validate(record)
        return record

    @staticmethod
    def xdg_mimeinfo() -> str | None:
        return None


class OctetStream(FileHandler):
    file_types = (Mime.MIMEtype("application/octet-stream"),)


class Directory(FileHandler):
    file_types = (Mime.MIMEtype("inode/directory"),)

    @classmethod
    def matches(cls, root, path, guesses) -> int | None:
        """Return 0..100 if this handler can handle the path, otherwise None."""
        if (root / path).is_dir():
            # Other directory-like datasets take precedence
            return 0
        else:
            return None


class Symlink(FileHandler):
    file_types = (Mime.MIMEtype("inode/symlink"),)

    @classmethod
    def matches(cls, root, path, guesses) -> int | None:
        """Return 0..100 if this handler can handle the path, otherwise None."""
        if (root / path).is_symlink():
            return 50
        else:
            return None


class EMPAD(FileHandler):
    file_types = (
        Mime.MIMEtype("application/x.empad+xml"),
        Mime.MIMEtype("application/x.empad-raw"),
    )

    def _find_all_members(self):
        # If database connection is available, use it
        if self.conn is not None:
            members = _get_dataset_members_from_db(self.conn, str(self.path))
            if members:
                return members

        # Fall back to filesystem-based discovery
        if Mime.MIMEtype("application/x.empad+xml") in self.guesses:
            found_raw = self.__find_raw(self.abspath)
            if found_raw is None:
                # Should not have matched otherwise
                raise DatasetConsistencyError("Did not find corresponding raw file")
            else:
                score, raw_file = found_raw
            return [self.path, raw_file.relative_to(self.root)]
        elif Mime.MIMEtype("application/x.empad-raw") in self.guesses:
            found_xml = self.__find_xml(self.abspath)
            if found_xml is None:
                # Should not have matched otherwise
                raise DatasetConsistencyError("Did not find corresponding XML file")
            else:
                score, xml_file = found_xml
            raw_path = self.path
            self._rebase(xml_file.relative_to(self.root))
            return [self.path, raw_path]
        else:
            raise DatasetConsistencyError("Should not happen")

    @classmethod
    def __find_xml(cls, abs_raw):
        containing_dir = os.path.dirname(abs_raw)
        # Look for XML files that could be the parent
        potential_xml = glob.glob("*.xml", root_dir=containing_dir) + glob.glob(
            "*.XML", root_dir=containing_dir
        )
        for f in potential_xml:
            abs_xml = os.path.join(containing_dir, f)
            res = cls.__match_xml(abs_xml, expected_rawpath=abs_raw)
            if res is not None:
                return (res, pathlib.Path(abs_xml))

    @classmethod
    def __find_raw(cls, abs_xml):
        # Adapted from https://github.com/LiberTEM/LiberTEM/blob/83313ca63e5c2325ebbca5d6170ff7b1d553d678/src/libertem/io/dataset/empad.py#L17
        # Licensed under MIT
        em = ET.parse(abs_xml)
        emroot = em.getroot()
        if emroot is None:
            return None
        raw_file = emroot.find("raw_file")
        if raw_file is None:
            return None
        raw_filename = raw_file.attrib["filename"]
        if raw_filename is None:
            return None
        filename = os.path.basename(raw_filename)
        path_raw = os.path.join(os.path.dirname(abs_xml), filename)
        if not os.path.exists(path_raw):
            return None
        return (50, pathlib.Path(path_raw))

    @classmethod
    def __match_xml(cls, abspath, expected_rawpath=None):
        # Adapted from https://github.com/LiberTEM/LiberTEM/blob/83313ca63e5c2325ebbca5d6170ff7b1d553d678/src/libertem/io/dataset/empad.py#L17
        # Licensed under MIT
        found_raw = cls.__find_raw(abspath)
        if found_raw is None:
            return None
        else:
            score, path_raw = found_raw
        # If the expected raw path is supplied, we only match the file
        # if the actual raw path matches the expected raw path
        if expected_rawpath is None:
            return score
        else:
            if (
                pathlib.Path(path_raw).resolve()
                == pathlib.Path(expected_rawpath).resolve()
            ):
                return score
            else:
                return None

    @classmethod
    def matches(cls, root, path, guesses):
        if Mime.MIMEtype("application/x.empad+xml") in guesses:
            return cls.__match_xml(root / path)
        elif Mime.MIMEtype("application/x.empad-raw") in guesses:
            found_xml = cls.__find_xml(root / path)
            if found_xml is not None:
                score, abspath = found_xml
                return score
        return None

    def get_mimes(self):
        return [Mime.MIMEtype("application/x.empad+xml"), Mime.MIMEtype("text/xml")]

    @staticmethod
    def xdg_mimeinfo():
        return """<mime-type type="application/x.empad-raw">
  <comment>Raw binary data component of EMPAD datasets</comment>
  <glob pattern="scan_x*_y*.raw" weight="80"/>
  <glob pattern="series_x*.raw" weight="80"/>
  <glob pattern="SCAN_X*_Y*.RAW" weight="80"/>
  <glob pattern="SERIES_X*.RAW" weight="80"/>
</mime-type>

<mime-type type="application/x.empad+xml">
  <comment>XML metadata component of EMPAD datasets</comment>
  <match>
    <magic type="string" offset="0" value="&lt;root name=">
      <magic type="string" offset="85:285" value="&lt;software_version&gt;"/>
    </magic>
  </match>
  <glob pattern="*.xml"/>
  <glob pattern="*.XML"/>
</mime-type>
"""
