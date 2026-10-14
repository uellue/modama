"""OAI-PMH protocol behaviour. Every response is validated against the OAI-PMH and oai_dc schemas."""

import os
import pwd

import pytest
from conftest import BASE_URL, DC, OAI
from modama_crawler.records import browse_url, oai_identifier
from werkzeug.test import Client

A = oai_identifier("/a.txt")
MISSING = oai_identifier("/missing.txt")


def errors(document) -> list[str]:
    return [error.get("code") for error in document.iter(f"{OAI}error")]


def identifiers(document) -> list[str]:
    return [element.text for element in document.iter(f"{OAI}identifier")]


def token(document) -> str | None:
    element = document.find(f".//{OAI}resumptionToken")
    return None if element is None else (element.text or "")


@pytest.mark.parametrize(
    "params, code",
    [
        ({}, "badVerb"),
        ({"verb": "Nonsense"}, "badVerb"),
        ({"verb": ["Identify", "Identify"]}, "badVerb"),
        ({"verb": "Identify", "extra": "x"}, "badArgument"),
        ({"verb": "GetRecord", "metadataPrefix": "oai_dc"}, "badArgument"),
        ({"verb": "GetRecord", "identifier": A, "metadataPrefix": ["oai_dc", "oai_dc"]}, "badArgument"),
        ({"verb": "GetRecord", "identifier": A, "metadataPrefix": "datacite"}, "cannotDisseminateFormat"),
        ({"verb": "GetRecord", "identifier": MISSING, "metadataPrefix": "oai_dc"}, "idDoesNotExist"),
        ({"verb": "ListMetadataFormats", "identifier": MISSING}, "idDoesNotExist"),
        ({"verb": "ListSets"}, "noSetHierarchy"),
        ({"verb": "ListRecords"}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "datacite"}, "cannotDisseminateFormat"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "set": "x"}, "noSetHierarchy"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": "2024-13-01"}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": "2024-06-01T00:00:00"}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": ""}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": "2024-06-01", "until": "2024-06-02T00:00:00Z"}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": "2024-06-02", "until": "2024-06-01"}, "badArgument"),
        ({"verb": "ListRecords", "metadataPrefix": "oai_dc", "from": "2030-01-01"}, "noRecordsMatch"),
        ({"verb": "ListIdentifiers", "metadataPrefix": "oai_dc", "until": "2023-12-31"}, "noRecordsMatch"),
        ({"verb": "ListRecords", "resumptionToken": "garbage"}, "badResumptionToken"),
        ({"verb": "ListRecords", "resumptionToken": "0,0,99999999999999999,1"}, "badResumptionToken"),
        ({"verb": "ListRecords", "resumptionToken": ",,0,0", "metadataPrefix": "oai_dc"}, "badArgument"),
    ],
)  # fmt: skip
def test_errors(oai, records, params, code):
    document = oai(**params)
    assert errors(document) == [code]
    request = document.find(f"{OAI}request")
    assert request.text == BASE_URL
    if code in ("badVerb", "badArgument"):
        assert request.attrib == {}
    else:
        assert request.get("verb") == params["verb"]


def test_identify(oai, records):
    identify = oai(verb="Identify").find(f"{OAI}Identify")
    assert identify.findtext(f"{OAI}baseURL") == BASE_URL
    assert identify.findtext(f"{OAI}protocolVersion") == "2.0"
    assert identify.findtext(f"{OAI}earliestDatestamp") == "2024-01-01T00:00:00Z"
    assert identify.findtext(f"{OAI}deletedRecord") == "no"
    assert identify.findtext(f"{OAI}granularity") == "YYYY-MM-DDThh:mm:ssZ"


def test_identify_empty(oai):
    identify = oai(verb="Identify").find(f"{OAI}Identify")
    assert identify.findtext(f"{OAI}earliestDatestamp") == "1970-01-01T00:00:00Z"


@pytest.mark.parametrize("params", [{}, {"identifier": A}])
def test_list_metadata_formats(oai, records, params):
    document = oai(verb="ListMetadataFormats", **params)
    prefixes = [e.text for e in document.iter(f"{OAI}metadataPrefix")]
    assert prefixes == ["oai_dc"]


def test_get_record(oai, records):
    document = oai(verb="GetRecord", identifier=A, metadataPrefix="oai_dc")
    assert identifiers(document) == [A]
    assert document.findtext(f".//{OAI}datestamp") == "2024-01-01T00:00:00Z"
    dc = {e.tag.removeprefix(DC): e.text for e in document.iter(f"{DC}*")}
    assert dc == {
        "title": "/a.txt",
        "creator": pwd.getpwuid(os.getuid()).pw_name,
        "publisher": "ER-C",
        "date": "1970-01-01T00:00:00Z",
        "type": "Dataset",
        "format": "text/plain",
        "identifier": browse_url("/a.txt"),
    }


@pytest.mark.parametrize("verb", ["ListRecords", "ListIdentifiers"])
def test_paging(oai, records, verb):
    """Pages of 2, 2 and 1 in datestamp order; the last one has an empty token."""
    document = oai(verb=verb, metadataPrefix="oai_dc")
    pages = [identifiers(document)]
    while token(document):
        document = oai(verb=verb, resumptionToken=token(document))
        pages.append(identifiers(document))
    assert pages == [records[0:2], records[2:4], records[4:5]]
    assert token(document) == ""
    assert (document.find(f".//{OAI}metadata") is None) == (verb == "ListIdentifiers")


def test_complete_list_has_no_token(oai, records):
    document = oai(verb="ListIdentifiers", metadataPrefix="oai_dc", until="2024-01-01")
    assert identifiers(document) == records[0:1]
    assert token(document) is None


def test_token_is_idempotent(oai, records):
    first = token(oai(verb="ListIdentifiers", metadataPrefix="oai_dc"))
    second = oai(verb="ListIdentifiers", resumptionToken=first)
    again = oai(verb="ListIdentifiers", resumptionToken=first)
    assert identifiers(second) == identifiers(again) == records[2:4]


@pytest.mark.parametrize(
    "from_, until, expected",
    [
        ("2024-06-01", None, slice(1, 5)),
        (None, "2024-06-01", slice(0, 4)),
        ("2024-06-01", "2024-06-01", slice(1, 4)),
        ("2024-06-01T12:00:00Z", "2024-06-01T23:59:59Z", slice(2, 4)),
        ("2024-06-01T12:00:01Z", None, slice(3, 5)),
        (None, "2024-06-01T11:59:59Z", slice(0, 2)),
    ],
)
def test_selective_harvesting(oai, records, from_, until, expected):
    """from and until are inclusive; tokens keep the range."""
    params = {"from": from_, "until": until}
    document = oai(
        verb="ListIdentifiers",
        metadataPrefix="oai_dc",
        **{k: v for k, v in params.items() if v is not None},
    )
    found = identifiers(document)
    while token(document):
        document = oai(verb="ListIdentifiers", resumptionToken=token(document))
        found += identifiers(document)
    assert found == records[expected]


def test_post(oai, records):
    document = oai("POST", verb="ListIdentifiers", metadataPrefix="oai_dc")
    assert identifiers(document) == records[0:2]


def test_method_not_allowed(server):
    response = Client(server).put("/oai", data={"verb": "Identify"})
    assert response.status_code == 405


def test_invalid_xml_characters(oai, add_record):
    """File names can contain characters that XML can't represent."""
    identifier = add_record("/bell\x07.txt", "2024-01-01T00:00:00Z")
    document = oai(verb="GetRecord", identifier=identifier, metadataPrefix="oai_dc")
    assert document.findtext(f".//{DC}title") == "/bell�.txt"
    assert identifiers(document) == [identifier]
