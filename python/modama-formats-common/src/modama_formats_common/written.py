"""The file's text as the record shows it (change text-as-written): as written up to TEXT
characters, else its head and tail; a line that may hold a credential left out.

The one home of that rule for the areas text and structured and for any format that shows
a text file (spec formats/text, "The text as written", "Head and tail of a long text",
"The tail of a file larger than the head", "A credential is left out of the text").
"""

import codecs
import contextlib
import os
from dataclasses import dataclass

from modama_crawler.extraction import MAX_STRING
from modama_crawler.formats.values import credential

# Characters of the text: one stored string (design D3)
TEXT = MAX_STRING
# Characters of the head and of the tail of a longer text
HALF = 2000
# Bytes read of a file's end beyond the head the format read
TAIL = 16 << 10
CREDENTIAL = "… (a line left out: may be a credential)"
FRONT_MATTER = "… (front matter left out: it may hold a credential)"


@dataclass(frozen=True)
class Shown:
    text: str  # values["text"]
    credentials: int  # lines shown as CREDENTIAL
    whole: bool  # the text is all of the file, as written


def gap(n: int, unit: str) -> str:
    return f"… {n:,} {unit} left out …\n"


def wide(encoding: str) -> bool:
    """An encoding in which a line feed is not the byte 0x0A alone."""
    return encoding.upper().replace("_", "-").startswith(("UTF-16", "UTF-32"))


def size_of(text: str, encoding: str) -> int:
    """Bytes of text in encoding, without a byte order mark."""
    name = codecs.lookup(encoding).name
    if name == "utf-8-sig":
        name = "utf-8"
    elif wide(name):
        name = name.split("-")[0] + "-" + name.split("-")[1] + "-le"
    return len(text.encode(name, "replace"))


def lines_of(data: bytes, encoding: str, final: bool) -> list[tuple[int, str]]:
    """(bytes, text) of each line of data, its line end (CRLF, CR or LF) as a line feed."""
    if wide(encoding):
        text = codecs.getincrementaldecoder(encoding)("replace").decode(data, final)
        return [(size_of(line, encoding), _lf(line)) for line in text.splitlines(True)]
    decoder = codecs.getincrementaldecoder(encoding)("replace")
    raw = data.splitlines(keepends=True)
    return [
        (len(line), _lf(decoder.decode(line, final and i == len(raw) - 1)))
        for i, line in enumerate(raw)
    ]


def _lf(line: str) -> str:
    stripped = line.rstrip("\r\n")
    return stripped + "\n" if len(stripped) < len(line) else stripped


def guarded(lines: list[tuple[int, str]]) -> tuple[list[tuple[int, str]], int]:
    """The lines with each that may hold a credential (the shared check) as CREDENTIAL, its indentation kept; how many."""
    out, n = [], 0
    for size, line in lines:
        content = line.rstrip("\n")
        if credential("", content):
            indent = content[: len(content) - len(content.lstrip())]
            line = indent + CREDENTIAL + line[len(content) :]
            n += 1
        out.append((size, line))
    return out, n


def front_matter_left_out(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """The lines with a front matter (`---` first, up to `---` or `...`) as one line FRONT_MATTER."""
    if not lines or lines[0][1].lstrip("﻿").rstrip("\n") != "---":
        return lines
    for i, (_, line) in enumerate(lines[1:], 1):
        if line.rstrip("\n") in ("---", "..."):
            size = sum(s for s, _ in lines[: i + 1])
            return [(size, FRONT_MATTER + "\n"), *lines[i + 1 :]]
    return [(sum(s for s, _ in lines), FRONT_MATTER + "\n")]


def _from_start(lines, budget: int):
    taken, chars = [], 0
    for size, line in lines:
        if chars + len(line) > budget:
            break
        taken.append((size, line))
        chars += len(line)
    return taken


def head_and_tail(
    head: list[tuple[int, str]],
    tail: list[tuple[int, str]],
    total: int,
    encoding: str,
    unit: str,
) -> str:
    """The lines of head that fit in HALF characters, a gap line, the lines of tail that
    fit in HALF characters from its end; a line longer than HALF cut at a character."""
    first = _from_start(head, HALF)
    if not first and head:
        line = head[0][1][:HALF]
        first = [(size_of(line, encoding), line)]
    last = _from_start(reversed(tail), HALF)[::-1]
    if not last and tail:
        line = tail[-1][1][-HALF:]
        last = [(size_of(line, encoding), line)]
    shown = "".join(line for _, line in first)
    if not shown.endswith("\n"):
        shown += "\n"
    left = total - sum(s for s, _ in first) - sum(s for s, _ in last)
    return shown + gap(left, unit) + "".join(line for _, line in last)


def shown(
    data: bytes,
    encoding: str,
    size: int,
    tail: bytes | None = None,
    front_matter: bool = False,
) -> Shown:
    """The text of a file whose first bytes are data (all of it when len(data) == size),
    tail its last bytes read beyond them (their first, partial line is dropped here);
    front_matter: a front matter is left out as a whole (Markdown, design D6)."""
    complete = len(data) >= size
    lines = lines_of(data, encoding, final=complete)
    if front_matter:
        lines = front_matter_left_out(lines)
    lines, secrets = guarded(lines)
    if complete:
        text = "".join(line for _, line in lines)
        if len(text) <= TEXT:
            return Shown(text, secrets, True)
        cut = len(_from_start(lines, HALF)) or 1
        end = lines[cut:] or lines[-1:]  # one long line: its end
    else:
        if lines and not lines[-1][1].endswith("\n"):
            lines = lines[:-1]  # cut by the head's end
        end = []
        if tail is not None and not wide(encoding):
            newline = tail.find(b"\n")
            end = (
                lines_of(tail[newline + 1 :], encoding, final=True)
                if newline >= 0
                else []
            )
            end, n = guarded(end)
            secrets += n
    text = head_and_tail(lines, end, size, encoding, "bytes")
    return Shown(text, secrets, False)


def shown_text(text: str) -> str:
    """A text of ours (a rendering) as head and tail when longer than TEXT, the gap in characters."""
    if len(text) <= TEXT:
        return text
    lines = [(len(line), line) for line in text.splitlines(True)]
    cut = len(_from_start(lines, HALF)) or 1
    return head_and_tail(lines, lines[cut:], len(text), "utf-8", "characters")


def read_tail(path: str, size: int, start: int) -> bytes:
    """The last TAIL bytes of the file at path, not before start (the end of the head read), without readahead."""
    offset = max(start, size - TAIL)
    with open(path, "rb", buffering=0) as f:
        if hasattr(os, "posix_fadvise"):
            with contextlib.suppress(OSError):
                os.posix_fadvise(f.fileno(), 0, 0, os.POSIX_FADV_RANDOM)
        f.seek(offset)
        data = b""
        while len(data) < size - offset and (
            chunk := f.read(size - offset - len(data))
        ):
            data += chunk
    return data


def of_head(found, path: str, front_matter: bool = False, tail: bool = True) -> Shown:
    """The text of a file whose head the text area read (`text.head.Head`), its tail
    read here where needed; tail False: none read (a file typed by its content)."""
    tail = tail and not found.complete and not wide(found.encoding)
    end = read_tail(path, found.size, len(found.data)) if tail else None
    return shown(found.data, found.encoding, found.size, end, front_matter)
