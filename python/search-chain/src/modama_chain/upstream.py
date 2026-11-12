"""What the browser knows of the code after the crawler: the harvester, the warehouse, the search API, matchmaker.

The second kind of upstream knowledge next to `warehouse.py` (which reads
their stores): code run or emulated (change chain-browse, D1). Upstream's
own files are used where they can run here, the harvester's XSLT and the
warehouse's transformation functions, loaded from the pinned submodules (a
read-only mount in the stack); the rest is emulated with the file and lines
it follows, in each function's docstring and in `SOURCES`, which the page
shows. Each emulation of a service declares the version and patches it
follows (`HIT`, `ENTRY`), which `sync.py` compares with what the search stack
builds.
"""

from __future__ import annotations

import importlib.util
import json
import re
from functools import cache
from pathlib import Path
from types import ModuleType

from lxml import etree

from .sync import Follows

OAI_NS = "http://www.openarchives.org/OAI/2.0/"


class Upstream:
    """The submodules' files: `harvester` holds dc_to_datacite.xsl, `warehouse` the warehouse's src/ and config/."""

    def __init__(self, harvester: Path, warehouse: Path):
        self.harvester = Path(harvester)
        self.warehouse = Path(warehouse)

    @cache  # noqa: B019 -- one instance per server process
    def xslt(self) -> etree.XSLT:
        return etree.XSLT(etree.parse(str(self.harvester / "dc_to_datacite.xsl")))

    def datacite(self, record_xml: str) -> str:
        """The harvester's conversion of one oai_dc `<record>` to DataCite, as `apply_xslt_transform` makes it.

        harvester_oaipmh.py:21-35: `ET.fromstring(xml.encode("utf-8"))`, the
        transform, `ET.tostring(result, pretty_print=True, encoding="UTF-8")`;
        its input is `ET.tostring(record.xml, pretty_print=True,
        encoding="unicode")` of oaipmh-scythe's record (process_record, :158).
        """
        result = self.xslt()(etree.fromstring(record_xml.encode("utf-8")))
        return etree.tostring(result, pretty_print=True, encoding="UTF-8").decode()

    @cache  # noqa: B019
    def _module(self, name: str) -> ModuleType:
        """A module of the warehouse's src/utils, loaded from its file, without putting `utils` on sys.path."""
        path = self.warehouse / "src" / "utils" / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"_warehouse_{name}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @cache  # noqa: B019
    def _validator(self):
        from jsonschema.validators import validator_for

        schema = json.loads((self.warehouse / "config" / "schema.json").read_text())
        cls = validator_for(schema)
        cls.check_schema(schema)
        return cls(schema)

    def document(
        self, datacite_xml: str, oai_dc_record: str, repo: str | None, harvest_url: str
    ) -> dict:
        """The warehouse's index document of one record: transform_core.py:149-188 and embedding_utils.py:70-76, without `emb`.

        The functions are the warehouse's; the steps between them are
        emulated. Raises ValueError with the warehouse's reason where it would
        skip the record or store an error for it.
        """
        import xmltodict
        from jsonschema.exceptions import best_match

        handle_xml = self._module("handle_xml")
        normalize = self._module("normalize_datacite_json")
        root = etree.fromstring(datacite_xml.encode("utf-8"))
        metadata_ns = handle_xml.detect_metadata_namespace(root)
        payload_ns = handle_xml.detect_payload_namespace(root)
        contents = handle_xml.preprocess_xml(root)
        converted = xmltodict.parse(contents, process_namespaces=True)
        record, meta = f"{OAI_NS}:record", f"{OAI_NS}:metadata"
        if record not in converted or meta not in converted[record]:
            raise ValueError(f"skipped by the warehouse: no {meta} in the record")
        found = handle_xml.get_resource(
            converted[record][meta], metadata_ns, payload_ns
        )
        if found is None:
            raise ValueError("skipped by the warehouse: no resource element")
        resource, namespace = found
        normalized = normalize.normalize_datacite_json(resource, namespace)
        # jsonschema.validate as patch 0001 does it in the image: one validator, best_match
        error = best_match(self._validator().iter_errors(normalized))
        if error is not None:
            raise ValueError(f"the warehouse's validation fails: {error.message}")
        return {
            **normalized,
            "_additional_metadata": oai_dc_record,
            "_repo": repo,
            "_harvest_url": harvest_url,
        }


# What search_hit follows: the search API's image version and our patches/search-api/ (sync.py)
HIT = Follows(
    "search-api",
    "0.10.2",
    "907335c419cb60905a59874cef4fe2693f52faa11abcf3c7de0dd09ca5abce04",
)

# SearchHitSrc and its nested models (models.py:131-179): field -> default, by alias, as FastAPI dumps them
_CREATOR = {"creatorName": None}  # extra fields kept (model_config extra="allow")
_SUBJECT = {
    "subject": None,
    "lang": None,
    "subjectScheme": None,
    "schemaUri": None,
    "valueUri": None,
    "classificationCode": None,
}
_TITLE = {"title": None, "lang": None}
_DESCRIPTION = {"description": None, "lang": None, "descriptionType": None}
_DATE = {"date": None, "dateType": None}


def _items(values, fields: dict, extra: bool = False) -> list[dict] | None:
    if values is None:
        return None
    return [
        {**fields, **{k: v for k, v in item.items() if extra or k in fields}}
        for item in values
    ]


def search_hit(doc_id: str, source: dict, score: float | None = None) -> dict:
    """The search API's hit for an index document, as `/search` returns it (models.py:182-251), emulated.

    `_score` and `score` come from a query; the live hit has neither.
    """
    src = {
        "doi": source.get("doi"),
        "url": source.get("url"),
        "_harvest_url": source.get("_harvest_url"),
        "_repo": source.get("_repo"),
        "titles": _items(source.get("titles", []), _TITLE),
        "descriptions": _items(source.get("descriptions", []), _DESCRIPTION),
        "publicationYear": source.get("publicationYear"),
        "dates": _items(source.get("dates"), _DATE),
        "subjects": _items(source.get("subjects"), _SUBJECT),
        "creators": _items(source.get("creators"), _CREATOR, extra=True),
        "resourceType": source.get("resourceType", "dataset"),
    }
    if src["doi"]:  # dataset_url, :200-215
        doi = src["doi"]
        url = (
            doi
            if doi.startswith("http")
            else f"https://doi.org/{doi.removeprefix('doi:')}"
        )
    else:
        url = src["url"] or (doc_id if doc_id.startswith("http") else None)
    titles, descriptions = src["titles"], src["descriptions"]
    return {
        "_id": doc_id,
        "_source": src,
        "_score": None,
        "score": score,
        "fileExtensions": [],
        "relevantTools": [],
        "dataset_url": url,
        "title": next(  # :217-225
            (t["title"] for t in titles if t["lang"] == "en"),
            titles[0]["title"] if titles else None,
        ),
        "description": next(  # :227-235
            (d["description"] for d in descriptions if d["lang"] == "en"),
            descriptions[0]["description"] if descriptions else None,
        ),
        "creator": next((c["creatorName"] for c in src["creators"]), None)  # :237-242
        if src["creators"]
        else None,
        "publication_date": next(  # :244-251
            (d["date"] for d in src["dates"] or () if d["dateType"] == "Issued"), None
        ),
    }


# matchmaker's cited dataset entry, expanded: the values it shows (D10)

# What cited_entry follows: matchmaker's commit and our patches/matchmaker/ (sync.py)
ENTRY = Follows(
    "matchmaker",
    "e7138c898926ebb79e45dd7d20cbf838dcf5dbe5",
    "d4ef3bf6203bf7469bf9c23b877eabced0ff443fd9f08269facbf1da8d41f6f9",
)

DESCRIPTION_LIMIT = 300  # SearchResultItem.tsx:67
AUTHORS_SHOWN = 3  # :74
SUBJECTS_SHOWN = 5  # :135
_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": '"',
    "&#39;": "'",
    "&apos;": "'",
    "&copy;": "©",
    "&reg;": "®",
    "&trade;": "™",
    "&bull;": "•",
    "&middot;": "·",
}


def strip_html(html: str) -> str:
    """utils.ts:65-89 stripHtml."""
    if not html:
        return ""
    text = re.sub(
        r"<(script|style|noscript|iframe)[^>]*>[\s\S]*?</\1>",
        "",
        html,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(
        r"&(nbsp|amp|lt|gt|quot|#39|apos|copy|reg|trade|bull|middot);",
        lambda m: _ENTITIES[m[0]],
        text,
    )


def publication_date(date: str) -> str:
    """utils.ts:197-210 formatPublicationDate, for the forms the warehouse writes (a year, an ISO date)."""
    trimmed = date.strip()
    if re.fullmatch(r"\d{4}", trimmed):
        return trimmed
    if m := re.match(r"(\d{4})-(\d{2})-(\d{2})", trimmed):
        return f"{m[1]}.{m[2]}.{m[3]}"
    return trimmed


def cited_entry(hit: dict, number: int = 1) -> dict:
    """What matchmaker's expanded "Datasets cited in this answer" row shows for a hit (CitedDatasets.tsx:69-115)."""
    src = hit["_source"]
    creators = [c.get("creatorName") or "" for c in src.get("creators") or []]
    date = hit.get("publication_date") or src.get("publicationYear")  # utils.ts:188-189
    byline = ", ".join(creators[:2]) + (
        f", +{len(creators) - 2} more" if len(creators) > 2 else ""
    )
    description = strip_html(hit.get("description") or "")
    subjects = [s["subject"] for s in src.get("subjects") or []]
    score = hit.get("score")
    return {
        "number": number,
        "repository": src.get(
            "_repo"
        ),  # repoProvenance.ts:160-171, unknown codes as text
        "title": hit.get("title"),
        "meta": " · ".join(x for x in (date and date[:4], byline) if x),
        # SearchResultItem.tsx:202 with utils.ts:217-226 sanitizeLinkHref: http(s) only (the
        # browser's URL normalisation is not emulated)
        "source": hit["_id"] if re.match(r"https?://", hit["_id"]) else None,
        "relevance": None  # SearchResultItem.tsx:27-48
        if not isinstance(score, int | float)
        else (100 if score >= 1 else min(99, round(max(0, score) * 100))),
        # characters here, UTF-16 code units in JavaScript: differs only beyond the BMP
        "description": description[:DESCRIPTION_LIMIT]
        + ("..." if len(description) > DESCRIPTION_LIMIT else ""),
        "description_full": description,
        "creators": creators[:AUTHORS_SHOWN],
        "creators_more": max(0, len(creators) - AUTHORS_SHOWN),
        "creators_all": creators,
        "date": publication_date(date) if date else None,
        "subjects": subjects[:SUBJECTS_SHOWN],
        "subjects_more": max(0, len(subjects) - SUBJECTS_SHOWN),
    }


# The emulations of a service, by view key, with what they follow (sync.py checks them)
FOLLOWS = {"hit": HIT, "entry": ENTRY}

# Shown on the page next to each view: what runs, and where it comes from
SOURCES = {
    "datacite": (
        "actual code",
        (
            "upstream's dc_to_datacite.xsl (metadata-crawlers 9c120f5, the Airflow image's"
            " HARVESTER_REF); the call emulated from harvester/harvester_oaipmh.py:21-35, 77-86"
        ),
    ),
    "document": (
        "actual code",
        (
            "the warehouse's handle_xml, normalize_datacite_json and config/schema.json"
            " (metadata-warehouse v1.10.0); the loop body of transform/transform_core.py:149-188"
            " and the fields of utils/embedding_utils.py:70-76 emulated; no `emb`"
        ),
    ),
    "hit": (
        "emulated",
        (
            f"SearchHit of {HIT.short()} (the image's"
            " src/data_commons_search/models.py:131-251), as /search serialises it; no score"
        ),
    ),
    "entry": (
        "emulated",
        (
            f"{ENTRY.short()}: src/components/CitedDatasets.tsx:69-115,"
            " SearchResultItem.tsx:27-152, src/lib/utils.ts:65-89, 188-210, repoProvenance.ts:160-171"
        ),
    ),
}
