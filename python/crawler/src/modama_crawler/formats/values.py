"""Whether a value from a file can be shown as text, one check for the formats of every collection.

@weber (2026-11-12, TEMPLATE.md): skip "tags with content that is not suitable
for text display (too large, binary data)". The limits, from RosettaSciIO's
110 DM test files and the K2IS fixture Capture52 (2026-11-12; moved here from
modama_formats_em.values):
"""

import re

# Lists and arrays: the longest list of values about the data seen is 4 items
# (a binning, a read area); the shortest blob or array of measured values 60
# (GMS's PageSetup.Win32, a Windows structure as bytes) and 67 (a CL
# detector's Saturation fraction, up to 28,776 in an EELS spectrum image)
MAX_ITEMS = 16
# Strings: the longest seen is 115 characters (a Windows path, Group Save.saved as)
MAX_CHARS = 1000
# Control characters but tab, line feed and carriage return (Windows line ends)
CONTROL = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
# RosettaSciIO's DM reader puts this group where it skips an array it does not
# read (the image data, ImageData.Data): where it is, not what it holds
UNREAD = frozenset({"size", "size_bytes", "offset", "endian"})


def textual(value) -> bool:
    """Whether value can be shown as text: not binary, not too large, not a marker for data not read.

    A dict is a tag group: textual unless it is RosettaSciIO's marker of an unread array.
    """
    if isinstance(value, bytes | bytearray):
        return False
    if isinstance(value, str):
        return len(value) <= MAX_CHARS and not CONTROL.search(value)
    if isinstance(value, dict):
        return set(value) != UNREAD
    if isinstance(value, list | tuple):
        return len(value) <= MAX_ITEMS and all(textual(v) for v in value)
    # NumPy arrays and scalars, without importing NumPy: numbers only
    if (dtype := getattr(value, "dtype", None)) is not None:
        return dtype.kind in "biuf" and getattr(value, "size", 1) <= MAX_ITEMS
    return True


# Credentials, best effort (change common-structured, review of 2026-11-12):
# configuration files hold passwords and tokens, and a record is seen by more
# people than the file. Erring on the side of leaving out: max_tokens and
# authentication_type go too; author does not
SECRET = (
    r"passw(or)?d|pwd|passphrase|secret|token|api[-_]?key|private[-_]?key"
    r"|credential|authorization|auth(?!or)"
    # names that end in _PASS or _PW (DB_PASS, SMTP_PW; review of text-as-written)
    r"|_pass(?![a-z])|_pw(?![a-z])"
)
SECRET_NAME = re.compile(SECRET, re.IGNORECASE)
# A PEM private key's first line (RFC 7468: "-----BEGIN PRIVATE KEY-----"; OpenSSH
# and OpenSSL write OPENSSH, RSA, EC, ENCRYPTED … before it); not a certificate
PRIVATE_KEY_BEGIN = r"-----BEGIN [A-Z0-9 ]{0,40}PRIVATE KEY-----"
# Tokens by their documented prefixes: GitHub ("GitHub's token formats",
# docs.github.com, About authentication to GitHub), GitLab ("Token prefixes",
# docs.gitlab.com/security/tokens), Slack ("Token types", docs.slack.dev), AWS
# access key IDs ("Understanding unique ID prefixes", AKIA and ASIA, AWS IAM
# User Guide, IAM identifiers); the number of characters after them is ours
TOKEN = (
    r"\b(?:ghp_|gho_|ghu_|ghs_|ghr_|github_pat_"
    r"|glpat-|gloas-|gldt-|glrtr?-|glcbt-|glptt-|glft-|glimt-|glagent-|glwt-"
    r"|glsoat-|glffct-|xoxb-|xoxp-|xapp-|xoxe\.xapp-|xwfp-)[\w.-]{8,}"
    r"|\b(?:AKIA|ASIA)[A-Z0-9]{12,}\b"
)
# Every branch costs linear time in the text (review of text-as-written: a line
# of " --" and "pass" repeated took hours): a name is matched from its start
# only, its secret word found once (atomic), the rest possessive
SECRET_VALUE = re.compile(
    # such a name, then = or : and a value (POSTGRES_PASSWORD=x, "token": x)
    rf"(?<![\w-])(?>[\w-]*?(?:{SECRET}))[\w-]*+[\"']?\s*+[=:]\s*+\S"
    # a command line's option (--requirepass x, --password=x)
    rf"|(?:^|(?<=\s))--?(?>[\w-]*?(?:{SECRET}|pass))[\w-]*+[\s=]++\S"
    # a URL with a user's password (postgres://admin:x@db/x)
    r"|://[^/@\s:]*+:[^/@\s]*+@"
    # an HTTP authorization's value (Basic …, Bearer …): a token of 8 or more
    # characters with a digit, +, / or = (not "Basic settings")
    r"|\b(?:Basic|Bearer)\s++(?=[\w+/=.-]*?[\d+/=])[\w+/=.-]{8,}"
    rf"|{PRIVATE_KEY_BEGIN}|{TOKEN}",
    re.IGNORECASE,
)


# A line that starts with such a name and `=` or `:`, its value maybe on the next lines
# (INI's continuation, a YAML block; review of text-as-written, M3)
SECRET_NAME_LINE = re.compile(
    rf"\s*+[\"']?(?>[\w.-]*?(?:{SECRET}))[\w.-]*+[\"']?\s*+[=:]", re.IGNORECASE
)


def credential_line(line: str) -> bool:
    """Whether a line of a text may hold a credential: as credential() finds it in a
    text, or a name of SECRET that starts the line, followed by `=` or `:`, a value or not."""
    return bool(SECRET_NAME_LINE.match(line)) or credential("", line)


def credential(name: str, value) -> bool:
    """Whether a value may be a credential, by its name (a dotted path) or its text, best effort.

    True when the name has a word of SECRET or holds what a text may not, or a
    text (or a text in a list) has such a word followed by `=` or `:` and a
    value, a command line option with such a word or `pass` and a value, a URL
    with a password, an HTTP authorization's value, a private key's first line
    or a token with a documented prefix. The formats leave such values out.
    """
    if SECRET_NAME.search(name) or SECRET_VALUE.search(name):
        return True
    texts = value if isinstance(value, list | tuple) else [value]
    return any(isinstance(t, str) and SECRET_VALUE.search(t) for t in texts)
