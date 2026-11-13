"""A parsed JSON, YAML or TOML document shortened in place: valid JSON, every key of what
it shows, long lists and texts cut with markers, credentials left out (change
text-as-written, design D1 option B; spec formats/structured, "A long document shortened
in place", "Shorter steps until it fits", "A credential in a structured document").

The limits come in steps, as `reprlib`'s maxlist and maxstring limit a representation:
first the shared check's (16 items, a text not suitable for text left out), then 3 items
and 200 characters, then 1 item and 80 characters.
"""

import json

from modama_crawler.formats.values import MAX_ITEMS, SECRET_VALUE, credential, textual

from .. import written
from .entries import MAX_VISITS, plain

# (items per list, characters per text; None: the shared check decides)
STEPS = ((MAX_ITEMS, None), (3, 200), (1, 80))
SECRET = "… (left out: may be a credential)"
NAME = "… (a name left out: may be a credential)"
MORE = "… (more values left out)"  # after MAX_VISITS values: an alias bomb


def items(n: int) -> str:
    return f"… ({n:,} more items)"


def characters_left_out(n: int) -> str:
    return f"… ({n:,} characters left out)"


def more_characters(n: int) -> str:
    return f"… ({n:,} more characters)"


class _TooLong(Exception):
    """The rendering is longer than its budget: no use making the rest of it."""


class _Walk:
    def __init__(self, keep: int, chars: int | None, budget: int | None = None):
        self.keep, self.chars, self.visits = keep, chars, 0
        # At least these characters: names and leaves, without quotes and separators
        self.budget, self.least = budget, 0

    def node(self, value, path: str):
        """value shortened; paths as entries.of_data writes them, for the credential check."""
        self.visits += 1
        if self.visits > MAX_VISITS:
            return MORE
        if isinstance(value, dict):
            self.count(sum(len(str(k)) for k in value))
            # A name that holds what a text may not (a URL with a password) is
            # left out too, not only its value (review of text-as-written, S1)
            return {
                (NAME if SECRET_VALUE.search(str(k)) else k): self.node(
                    v, f"{path}.{k}" if path else str(k)
                )
                for k, v in value.items()
            }
        if isinstance(value, list):
            if any(isinstance(v, dict | list) for v in value):
                out = [
                    self.node(v, f"{path}[{i}]")
                    for i, v in enumerate(value[: self.keep], 1)
                ]
            else:
                # The items shown, as entries.kept checks a list: textual ones only
                shown = [plain(v) for v in value[: self.keep]]
                if credential(path, [v for v in shown if textual(v)]):
                    return SECRET
                out = [self.leaf(v, path, alone=False) for v in shown]
            if len(value) > self.keep:
                out.append(items(len(value) - self.keep))
            return out
        return self.leaf(value, path)

    def count(self, n: int) -> None:
        if self.budget is not None:
            self.least += n
            if self.least > self.budget:
                raise _TooLong

    def leaf(self, value, path: str, alone: bool = True):
        value = plain(value)
        # Every leaf as rendered has at least this many characters (a marker 20)
        self.count(min(len(str(value)), 20))
        if isinstance(value, str) and not textual(value):
            return characters_left_out(len(value))
        if alone and credential(path, value):
            return SECRET
        if isinstance(value, str) and self.chars and len(value) > self.chars:
            return value[: self.chars] + more_characters(len(value) - self.chars)
        return value


def rendering(
    documents: list, keep: int, chars: int | None, budget: int | None = None
) -> str | None:
    """The documents shortened by one step, one line of JSON each; None as soon as it
    is surely longer than budget."""
    walk = _Walk(keep, chars, budget)
    lines = []
    try:
        for i, document in enumerate(documents, 1):
            path = f"[{i}]" if len(documents) > 1 else ""
            node = walk.node(document, path)
            lines.append(json.dumps(node, ensure_ascii=False, separators=(", ", ": ")))
    except _TooLong:
        return None
    return "\n".join(lines)


def shortened(documents: list) -> str:
    """The first step's rendering that fits in written.TEXT characters, else the last one's head and tail.

    The last step first: where even it does not fit (a document of many keys), it is
    the only rendering made (review of text-as-written, S3)."""
    last = rendering(documents, *STEPS[-1])
    if len(last) > written.TEXT:
        return written.shown_text(last)
    for keep, chars in STEPS[:-1]:
        text = rendering(documents, keep, chars, budget=written.TEXT)
        if text is not None and len(text) <= written.TEXT:
            return text
    return last
