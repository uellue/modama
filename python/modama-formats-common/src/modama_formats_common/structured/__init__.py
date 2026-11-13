"""Structured data files: JSON, YAML, TOML, CSV, XML, INI and .cfg, each a single-file dataset described by what it says.

Read with the established readers (json, tomllib, csv, configparser from the
standard library; PyYAML's safe loader as ..yamldoc changes it; defusedxml), whole
documents of at most LIMIT bytes, and kept as flat entries (entries.py) but one
skip list; spec formats/structured. These formats run after the domain formats
and claim only the generic types: a subtype (EMPAD's header, SVG, a notebook)
keeps its own.
"""

import configparser
import contextlib
import csv
import io
import json
import os
import tomllib
from collections.abc import Iterable
from pathlib import Path

import defusedxml.ElementTree as ET
import yaml
from modama_crawler.formats import (
    Collection,
    Dataset,
    Directory,
    Entry,
    Extracted,
    Format,
)

from .. import written, yamldoc
from ..text import head as text_head
from .entries import headline, kept, of_data, of_documents, of_xml
from .shortened import shortened

HERE = Path(__file__).parent
# Whole documents up to 8 MiB (spec "Bounded reading"). The October listing:
# above it only 5 JSON files (89 to 376 MB: traces, a package cache) and 3 XML
# files (10.5 to 26 MB, Quantum ESPRESSO output), data dumps whose first
# entries would be data; the next largest JSON is 5.7 MB, CSV 4.4 MB
LIMIT = 8 << 20
# Of a larger file: its first bytes, for the text's head and JSON Lines, and the
# last written.TAIL bytes for its tail; nothing parsed (change text-as-written)
LARGE_HEAD = 64 << 10
# What the readers raise for a file they refuse: shown as plain text instead
# (JSON, TOML and decoding errors are ValueErrors)
REFUSED = (ValueError, yaml.YAMLError, configparser.Error, RecursionError)
SAMPLE = 64 * 1024  # what csv.Sniffer sees
DELIMITERS = ",;\t|"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XSI = "http://www.w3.org/2001/XMLSchema-instance"
BOMS = (
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
)


def first_text(data: bytes) -> str:
    """The first bytes as text, without a byte order mark: Latin-1 where there is none, so that any byte reads."""
    for bom, codec in BOMS:
        if data.startswith(bom):
            return data[len(bom) :].decode(codec, "ignore")
    return data.decode("latin-1")


def decoded(data: bytes) -> tuple[str, str]:
    """A text file's content and its encoding: UTF-8 (a byte order mark dropped), else Latin-1."""
    try:
        return data.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1"


def bounded(path: str) -> tuple[bytes, int]:
    """The whole file and its size; of a file larger than LIMIT its first LARGE_HEAD bytes only."""
    with open(path, "rb", buffering=0) as f:
        size = os.fstat(f.fileno()).st_size
        if size > LIMIT:
            with contextlib.suppress(OSError):  # no readahead, as text.head.read
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
            return f.read(LARGE_HEAD), size
        data = f.read(LIMIT + 1)
    return data, max(size, len(data))


def refused(data: bytes, error: Exception) -> Extracted:
    """A file its reader refuses, as plain text: the reader's message, the text area's
    encoding and line count as the summary line, the text by the text area's rules."""
    encoding = text_head.encoding(data, complete=True)
    mapped = {"parse error": str(error), "encoding": encoding}
    values = {"original_metadata": {}, "mapped_metadata": mapped}
    if encoding is None:
        return Extracted(summary=[], subjects=[], values=values)
    text = text_head.decoded(data, encoding, complete=True)
    count = text_head.lines(text_head.Head(data, True, encoding, text, len(data)))
    mapped |= count
    shown = written.shown(data, encoding, len(data))
    values["text"] = shown.text
    if shown.credentials:
        mapped["credentials_left_out"] = shown.credentials
    summary = [encoding, *(f"{k} {v}" for k, v in count.items())]
    return Extracted(summary=summary, subjects=[], values=values)


def described(
    pairs: Iterable[tuple[str, object]], where: str, mapped: dict, skip=None
) -> tuple[list[str], dict]:
    """The summary line and the values of a document's pairs, with the cut and the credentials left out said in mapped."""
    original, cut, secrets = kept(pairs, where)
    if cut:
        mapped["cut_at_entries"] = len(original)
    if secrets:
        mapped["credentials_left_out"] = secrets
    line = headline(original, skip) if skip else headline(original)
    return line, {"original_metadata": original, "mapped_metadata": mapped}


class Document(Format):
    """A file of `type` as one dataset; `lies` may say from its first `head` bytes that it is not of that type."""

    # After the domain formats (image 50, EM 60 and up), which may claim these
    # files first, and before the text area (20), which claims the text/plain
    # these formats give a file whose content is not of its name's type
    # (recognition-checks-content D3: a format that drops types runs first)
    priority = 21
    head = 0  # bytes recognition reads for `lies`; 0: no check
    basis = "single file"

    def lies(self, data: bytes, e: Entry) -> str | None:
        """Why the file is not of its type, None if it may be."""
        return None

    def recognize(self, d: Directory) -> Iterable[Dataset]:
        for e in d.of_type(self.type):
            if self.head:
                try:
                    data = d.read(e, self.head)
                except OSError as error:
                    d.cannot_read(e, error)
                    continue
                if (reason := self.lies(data, e)) is not None:
                    d.not_of_type(e, reason)
                    continue
            yield Dataset(anchor=e.rel, basis=self.basis)

    # The file's text in values["text"] (change text-as-written); a file its
    # reader refuses shown as plain text, not failed
    shows_text = True

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        path = root + dataset.anchor
        data, size = bounded(path)
        if size > LIMIT:
            # A file that grew past LIMIT since fstat: its head as for any such file
            return self.over_the_bound(data[:LARGE_HEAD], size, path, dataset.anchor)
        try:
            summary, values, documents = self.describe(data, dataset.anchor)
        except REFUSED as error:
            if not self.shows_text:
                raise
            return refused(data, error)
        encoding = text_head.encoding(data, complete=True)
        if self.shows_text and encoding is not None and data:
            mapped = values["mapped_metadata"]
            shown = written.shown(data, encoding, len(data))
            # A walk cut by its bounds did not see every value: a credential may
            # be among those it did not see (review of text-as-written, M3)
            secret = (
                mapped.get("credentials_left_out")
                or shown.credentials
                or mapped.get("cut_at_entries") is not None
            )
            text = None
            if documents is not None and (secret or not shown.whole):
                # Longer than written.TEXT, or with a credential: shortened in
                # place, every key of what it shows (design D1, option B; D6)
                with contextlib.suppress(RecursionError):  # very deep: as written
                    text = shortened(documents)
            if text is not None:
                values["text"] = text
            else:
                values["text"] = shown.text
                if shown.credentials:
                    mapped["credentials_left_out"] = shown.credentials
        return Extracted(summary=summary, subjects=[], values=values)

    def describe(self, data: bytes, where: str) -> tuple[list[str], dict, list | None]:
        """The summary line, the values and the parsed documents (None: not JSON-like)."""
        raise NotImplementedError

    def over_the_bound(
        self, data: bytes, size: int, path: str, where: str
    ) -> Extracted:
        """A file larger than LIMIT: its head (data) and tail as text, nothing parsed."""
        mapped = {"not_parsed_larger_than_bytes": LIMIT}
        values = {"mapped_metadata": mapped}
        encoding = text_head.encoding(data, complete=False)
        if encoding is None or not self.shows_text:
            return Extracted(summary=[], subjects=[], values=values)
        tail = written.read_tail(path, size, len(data))
        shown = written.shown(data, encoding, size, tail)
        values["text"] = shown.text
        if shown.credentials:
            mapped["credentials_left_out"] = shown.credentials
        return Extracted(
            summary=self.head_summary(data, mapped, where), subjects=[], values=values
        )

    def head_summary(self, data: bytes, mapped: dict, where: str) -> list[str]:
        """The summary line of a file over the bound, from its head; none but for JSON Lines."""
        return []


class Json(Document):
    type = "application/json"
    reacts_to = frozenset({type})
    head = 64
    basis = "single file, a JSON value first"

    def lies(self, data: bytes, e: Entry) -> str | None:
        first = first_text(data).lstrip(" \t\r\n")[:1]
        if first and first in '{["-0123456789tfn':
            return None
        if not first and e.size > self.head:
            return None  # only whitespace in the first bytes: cannot tell
        return "no JSON value first"

    def describe(self, data: bytes, where: str):
        documents = json_documents(data)
        mapped = {"documents": len(documents)}
        return *described(of_documents(documents), where, mapped), documents

    def head_summary(self, data: bytes, mapped: dict, where: str) -> list[str]:
        """JSON Lines recognised from the head: at least two complete lines, each a JSON
        object or array on its own; the summary line from the first document."""
        documents = []
        for line in data.split(b"\n")[:-1]:  # the last line is cut by the head
            if not line.strip():
                continue
            try:
                document = json.loads(line, parse_constant=str, parse_float=as_written)
            except ValueError:
                return []
            if not isinstance(document, dict | list):
                return []
            documents.append(document)
        if len(documents) < 2:
            return []
        mapped |= {"json lines": True, "documents at least": len(documents)}
        return described(of_data(documents[0]), where, {})[0]


class JsonSchema(Json):
    """A JSON document that the core types by its `"$schema":` key, read as any JSON document."""

    type = "application/schema+json"
    reacts_to = frozenset({type})


def as_written(text: str) -> float | str:
    """A JSON or TOML float as a number where it prints as written, else its text
    (`1.0E-3`, `0.00001`, `1e999`): what the file says (spec "Values as the file writes them")."""
    value = float(text)
    return value if repr(value) == text else text


def json_documents(data: bytes) -> list:
    """The JSON document, or the lines of a JSON Lines file; NaN and the infinities as these words."""
    options = {"parse_constant": str, "parse_float": as_written}
    try:
        return [json.loads(data, **options)]
    except json.JSONDecodeError as error:
        if error.msg != "Extra data":
            raise
        try:
            return [
                json.loads(line, **options)
                for line in data.decode("utf-8-sig").splitlines()
                if line.strip()
            ]
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise error from None


class Yaml(Document):
    type = "application/yaml"
    reacts_to = frozenset({type})

    def describe(self, data: bytes, where: str):
        documents = yamldoc.documents(data)
        mapped = {"documents": len(documents)}
        return *described(of_documents(documents), where, mapped), documents


class Toml(Document):
    type = "application/toml"
    reacts_to = frozenset({type})

    def describe(self, data: bytes, where: str):
        # tomllib has no hook for integers: 0x1F and 1_000 come as 31 and 1000
        document = tomllib.loads(data.decode("utf-8-sig"), parse_float=as_written)
        return *described(of_data(document), where, {}), [document]


class Xml(Document):
    type = "application/xml"
    reacts_to = frozenset({type})
    head = 64
    basis = "single file, < first"

    def lies(self, data: bytes, e: Entry) -> str | None:
        first = first_text(data).lstrip(" \t\r\n")[:1]
        if first == "<" or (not first and e.size > self.head):
            return None
        return "no < first"

    # Its text is mostly markup (text-as-written, Q1); a document defusedxml
    # refuses fails, as a safety rule (D4)
    shows_text = False

    def describe(self, data: bytes, where: str):
        root, namespace, xsi = parse_xml(data)
        mapped = {"root": root.tag}
        if namespace is not None:
            mapped["namespace"] = namespace

        def plumbing(path: str) -> bool:
            # namespace declarations and xsi: attributes, not for the summary line
            last = path.rsplit(".", 1)[-1]
            return last.startswith("@xmlns") or last.split(":")[0][1:] in xsi

        summary, values = described(of_xml(root), where, mapped, plumbing)
        return [root.tag, *summary], values, None


def parse_xml(data: bytes):
    """The document's root with names as the file writes them, its namespace, and the prefixes of XSI.

    defusedxml refuses entity declarations and external references. An element's
    or attribute's name gets the prefix the file binds to its namespace (none
    for the default namespace), and a namespace declaration becomes an
    attribute `xmlns` or `xmlns:<prefix>` of the element that declares it.
    """
    scopes = [{XML_NS: "xml"}]
    declared: list[tuple[str, str]] = []
    xsi: set[str] = set()
    root = namespace = None
    for event, item in ET.iterparse(
        io.BytesIO(data), events=("start-ns", "start", "end")
    ):
        if event == "start-ns":
            declared.append(item)
            if item[1] == XSI:
                xsi.add(item[0])
            continue
        if event == "end":
            scopes.pop()
            continue
        scope = scopes[-1]
        if declared:
            scope = {**scope, **{uri: prefix for prefix, uri in declared}}
        scopes.append(scope)
        if root is None:
            root = item
            if item.tag.startswith("{"):
                namespace = item.tag[1:].partition("}")[0]
        attrib = {(f"xmlns:{p}" if p else "xmlns"): uri for p, uri in declared}
        attrib |= {qualified(k, scope): v for k, v in item.attrib.items()}
        declared = []
        item.tag = qualified(item.tag, scope)
        item.attrib.clear()
        item.attrib.update(attrib)
    return root, namespace, xsi


def qualified(name: str, scope: dict[str, str]) -> str:
    """A name `{uri}local` with the prefix the scope binds to uri: `prefix:local`, `local` for the default namespace."""
    if not name.startswith("{"):
        return name
    uri, _, local = name[1:].partition("}")
    prefix = scope.get(uri)
    return f"{prefix}:{local}" if prefix else local


class Csv(Document):
    type = "text/csv"
    reacts_to = frozenset({type})

    def extract(self, dataset: Dataset, root: str) -> Extracted:
        """The dialect, the header's names, the columns and the rows counted in the first LIMIT bytes; no data row."""
        with open(root + dataset.anchor, "rb", buffering=0) as f:
            data = f.read(LIMIT + 1)
        cut = len(data) > LIMIT
        if cut:  # the rows that end in the first LIMIT bytes
            data = data[: data.rfind(b"\n", 0, LIMIT) + 1]
        text, encoding = decoded(data)
        sample = text[:SAMPLE]
        if len(text) > SAMPLE:
            sample = sample[: sample.rfind("\n") + 1] or sample
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample, delimiters=DELIMITERS)
        except csv.Error:  # one column, or no delimiter among DELIMITERS
            dialect = None
        try:
            header = sniffer.has_header(sample)
        except csv.Error:
            header = False
        rows = (
            r
            for r in csv.reader(io.StringIO(text, newline=""), dialect or "excel")
            if r
        )
        first = next(rows, [])
        count = sum(1 for _ in rows) + (1 if first and not header else 0)
        mapped = {"encoding": encoding}
        if dialect is not None:
            mapped["delimiter"] = dialect.delimiter
        mapped |= {"header": header, "columns": len(first)}
        mapped["rows_at_least" if cut else "rows"] = count
        names = first if header else []
        pairs = (
            (f"column[{i}]" if len(names) > 1 else "column", name)
            for i, name in enumerate(names, 1)
        )
        summary, values = described(pairs, dataset.anchor, mapped)
        return Extracted(summary=summary, subjects=[], values=values)


class Ini(Document):
    type = "text/x-ini"
    reacts_to = frozenset({type})
    head = 1024
    basis = "single file, [section] first"

    def lies(self, data: bytes, e: Entry) -> str | None:
        for line in first_text(data).splitlines():
            line = line.strip()
            if line and line[0] not in "#;":
                return None if line.startswith("[") else "no [section] first"
        return None  # empty, or comments only: cannot tell

    def describe(self, data: bytes, where: str):
        text, encoding = decoded(data)
        # As found: names' case kept, no interpolation, [DEFAULT] a section like
        # any other (no name but NUL's can be the default section's), a repeated
        # key's last value (strict=False, as configparser reads it)
        parser = configparser.ConfigParser(
            interpolation=None, strict=False, allow_no_value=True, default_section="\0"
        )
        parser.optionxform = str
        parser.read_string(text, source=where)
        # Not shortened in place: an INI file is shown as written, line by line
        return *described(sections(parser), where, {"encoding": encoding}), None


def sections(parser: configparser.ConfigParser):
    """(section.key, value) of every key, a section without keys as {}."""
    for section in parser.sections():
        items = parser.items(section, raw=True)
        if not items:
            yield section, {}
        for key, value in items:
            yield f"{section}.{key}", value


class Cfg(Ini):
    """A .cfg file with a [section] first (or nothing but comments), read as INI."""

    type = "text/x-config"
    reacts_to = frozenset({type})


# This part of the collection, for its tests; the package's COLLECTION joins the parts.
COLLECTION = Collection(
    "structured",
    [Json(), JsonSchema(), Yaml(), Toml(), Csv(), Xml(), Ini(), Cfg()],
    mime_files=(HERE / "structured.xml",),
)
