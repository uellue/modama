"""Values not suitable for text (formats.values.textual), one test per kind; the
cases from real EM fixtures are in modama_formats_em/tests/test_values.py."""

import numpy as np
from modama_crawler.formats.values import MAX_CHARS, MAX_ITEMS, credential, textual


def test_a_large_list():
    assert textual([0.25] * MAX_ITEMS)
    assert not textual([0.25] * (MAX_ITEMS + 1))


def test_an_array_not_read():
    # RosettaSciIO's marker where it skips the image data: where it is, not what it holds
    assert not textual({"size": 1, "size_bytes": 4, "offset": 0, "endian": "<"})
    assert textual({"size": 1})


def test_a_long_string():
    # No fixture has one: the longest string in RosettaSciIO's 110 DM test files has 115 characters
    assert textual("x" * MAX_CHARS)
    assert not textual("x" * (MAX_CHARS + 1))


def test_control_characters():
    # No fixture has one; tab, line feed and carriage return are text
    assert textual("line 1\r\nline 2\tend")
    assert not textual("PK\x03\x04")
    assert not textual("a\x00b")


def test_bytes():
    assert not textual(b"\x00\x01")
    assert not textual(bytearray(b"ab"))


def test_numpy_arrays():
    # Numbers are text, objects and strings in an array are not; nor a large array
    assert textual(np.float64(2.0))
    assert textual(np.array([1, 2, 3]))
    assert not textual(np.array(["a", "b"]))
    assert not textual(np.array([object()]))
    assert not textual(np.zeros(MAX_ITEMS + 1))


# Credentials, best effort (the review of change common-structured, 2026-11-12)


def test_a_name_that_says_secret():
    for name in (
        "db.password",
        "db.Passwd",
        "pwd",
        "ssh.passphrase",
        "client_secret",
        "api_token",
        "apiKey",
        "private-key",
        "credentials.id",
        "headers.Authorization",
        "auth",
        "nextcloud.authentication_type",
    ):
        assert credential(name, "x"), name
    for name in ("author", "authors[1].name", "db.user", "key_size", "passive"):
        assert not credential(name, "x"), name


def test_a_compose_environment_list():
    assert credential("environment", ["POSTGRES_PASSWORD=hunter2", "POSTGRES_USER=u"])
    assert not credential("environment", ["POSTGRES_USER=u", "TZ=UTC"])


def test_a_command_line_option():
    assert credential("command", "redis-server --requirepass hunter2")
    assert credential("command", "tool --password=x")
    assert not credential("command", "redis-server /usr/local/etc/redis/redis.conf")


def test_a_url_with_a_password():
    assert credential("url", "postgres://admin:hunter2@db/x")
    assert not credential("url", "http://webdav:8080/")
    assert not credential("url", "https://user@example.org/")


def test_a_secret_name_in_a_text():
    assert credential("line", "pwd: hunter2")
    assert credential("line", '"token": "abc"')
    assert not credential("line", "the token bucket refills")


def test_an_authorization_value():
    assert credential("header", "Basic aHVudGVyMg==")
    assert credential("header", "Bearer eyJhbGciOi.eyJzdWIi.c2lnbmF0dXJl")
    assert not credential("note", "Basic settings of the stage")
