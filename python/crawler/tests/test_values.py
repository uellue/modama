"""Values not suitable for text (formats.values.textual), one test per kind; the
cases from real EM fixtures are in modama_formats_em/tests/test_values.py."""

import time

import numpy as np
import pytest
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


# Review of text-as-written (2026-11-13): what the file's text showed, and time


def test_a_private_key_block():
    for begin in ("OPENSSH PRIVATE KEY", "RSA PRIVATE KEY", "PRIVATE KEY"):
        assert credential("note", f"-----BEGIN {begin}-----"), begin
    assert not credential("note", "-----BEGIN CERTIFICATE-----")
    assert not credential("note", "-----BEGIN PUBLIC KEY-----")


def test_names_that_end_in_pass_or_pw():
    for name in ("DB_PASS", "db_pw", "SMTP_PASSWD"):
        assert credential(name, "x"), name
        assert credential("line", f"{name}=hunter2"), name
    for name in ("passport", "db_passive", "pwm_channel"):
        assert not credential(name, "x"), name


def test_well_known_token_prefixes():
    # GitHub (docs.github.com, "GitHub's token formats"), GitLab (docs.gitlab.com,
    # "Token prefixes"), Slack (docs.slack.dev, "Token types"), AWS access key
    # IDs (docs.aws.amazon.com, IAM, "Understanding unique ID prefixes")
    for token in (
        "ghp_aBcD1234eFgH5678iJkL",
        "github_pat_11ABCDEFG0123456789_abc",
        "gho_aBcD1234eFgH5678",
        "ghs_aBcD1234eFgH5678",
        "glpat-aBcD1234eFgH5678",
        "xoxb-1234-5678-aBcD",
        "xoxp-1234-5678-aBcD",
        "AKIAIOSFODNN7EXAMPLE",
    ):
        assert credential("note", f"use {token} here"), token
    for text in ("ghp_", "the gh tool", "AKIA", "glpat-", "xoxb-"):
        assert not credential("note", text), text


def test_pass_and_pw_as_a_whole_name():
    # Second review of text-as-written, S1: a document's key, not a word in prose
    for name in ("pass", "PW", "db.pass", "users[2].pw"):
        assert credential(name, "x"), name
    for name in ("passes", "pw_mode", "bypass"):
        assert not credential(name, "x"), name
    assert not credential("note", "pass: 3 of 5 samples")


def test_an_access_key_id_in_capitals_only():
    # Second review, S2: AWS writes its key IDs in capitals
    assert credential("note", "key AKIAIOSFODNN7EXAMPLE")
    assert not credential("note", "AsiaPacificSynchrotron2024: beamtime")
    assert not credential("note", "akiaiosfodnn7example")


def test_a_name_that_holds_a_url_with_a_password():
    assert credential("users.postgres://admin:hunter2key@db/x", 1)


@pytest.mark.parametrize(
    "line",
    [
        " --" + "pass" * 10_000,  # the option branch, 40 KB
        "password" * 5_000,  # a secret word repeated, 40 KB
        "://" + ":" * 40_000,  # the URL branch
        "Bearer " * 6_000,
        "-----BEGIN " + "A " * 20_000,
    ],
)
def test_a_long_adversarial_line_costs_linear_time(line):
    # A line 4 times as long takes about 4 times as long; quadratic, 16 times. The
    # ratio of this process's CPU times, not a bound in seconds: another suite
    # running beside it made one fail (1 MB took up to 0.45 s of a 0.5 s bound)
    def cpu(text: str) -> float:
        start = time.process_time()
        credential("line", text)
        return time.process_time() - start

    one = cpu(line * 25)  # 1 MB
    assert cpu(line * 100) < 8 * max(one, 0.01)
