"""The file's text as the record shows it (change text-as-written): as written up to TEXT
characters, else its head and tail; a line that may hold a credential left out.

The one home of that rule for the areas text and structured and for any format that shows
a text file (spec formats/text, "The text as written", "Head and tail of a long text",
"The tail of a file larger than the head", "A credential is left out of the text").

Only the lines that can be shown are checked for credentials, each at most TEXT
characters of it, so that a large file costs time in proportion to what is shown (review
of text-as-written, M1). A line is left out when the shared check flags it, when it is
within a private key block, or when it continues a flagged line: indented deeper, as an
INI value's continuation or a YAML block below its name (M2, M3).
"""

import codecs
import contextlib
import os
from collections.abc import Iterator
from dataclasses import dataclass

from modama_crawler.extraction import MAX_STRING
from modama_crawler.formats.values import credential_line

# Characters of the text: one stored string (design D3)
TEXT = MAX_STRING
# Characters of the head and of the tail of a longer text
HALF = 2000
# Bytes read of a file's end beyond the head the format read
TAIL = 16 << 10
CREDENTIAL = "… (a line left out: may be a credential)"
FRONT_MATTER = "… (front matter left out: it may hold a credential)"


def credentials_marker(n: int) -> str:
    return CREDENTIAL if n == 1 else f"… ({n} lines left out: may hold a credential)"


@dataclass(frozen=True)
class Shown:
    text: str  # values["text"]
    credentials: int  # lines left out as may holding a credential
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


def _lf(line: str) -> str:
    stripped = line.rstrip("\r\n")
    return stripped + "\n" if len(stripped) < len(line) else stripped


class _Text:
    """A file's lines as found: their bytes, decoded only where shown or checked."""

    def __init__(self, data: bytes, encoding: str, final: bool, front_matter=False):
        self.encoding, self.final = encoding, final
        if wide(encoding):
            text = codecs.getincrementaldecoder(encoding)("replace").decode(data, final)
            self.raw = text.splitlines(True)
            self.sizes = [size_of(line, encoding) for line in self.raw]
        else:
            self.raw = data.splitlines(keepends=True)
            self.sizes = [len(line) for line in self.raw]
            if codecs.lookup(encoding).name == "utf-8-sig" and self.sizes:
                # The byte order mark is not shown: it counts as left out
                self.sizes[0] -= len(codecs.BOM_UTF8)
        self._decoded: dict[int, str] = {}
        self._flagged: dict[int, bool] = {}
        scan = wide(encoding) or b"PRIVATE KEY-----" in data
        self.keys = self._private_keys() if scan else set()
        self.front = self._front_matter() if front_matter else None

    def __len__(self) -> int:
        return len(self.raw)

    def ends_line(self, i: int) -> bool:
        return self.raw[i][-1:] in ("\n", "\r", b"\n", b"\r")

    def text(self, i: int) -> str:
        if i not in self._decoded:
            raw = self.raw[i]
            if not isinstance(raw, str):
                last = i == len(self.raw) - 1
                decoder = codecs.getincrementaldecoder(self.encoding)("replace")
                raw = decoder.decode(raw, self.final or not last)
            self._decoded[i] = _lf(raw)
        return self._decoded[i]

    def _strip(self, i: int):
        raw = self.raw[i]
        return raw.lstrip(" \t" if isinstance(raw, str) else b" \t")

    def blank(self, i: int) -> bool:
        return not self.raw[i].strip()

    def indent(self, i: int) -> int:
        return len(self.raw[i]) - len(self._strip(i))

    def _has(self, i: int, *words: str) -> bool:
        raw = self.raw[i]
        return all((w if isinstance(raw, str) else w.encode()) in raw for w in words)

    def _private_keys(self) -> set[int]:
        """The lines of private key blocks, BEGIN to END (a fast scan of every line)."""
        inside, keys = False, set()
        for i in range(len(self.raw)):
            if not inside and self._has(i, "-----BEGIN", "PRIVATE KEY-----"):
                inside = True
            if inside:
                keys.add(i)
                if self._has(i, "-----END"):
                    inside = False
        return keys

    def _front_matter(self) -> int | None:
        """The index of the line that closes a front matter (`---` first), None without one."""
        if not self.raw or self.text(0).lstrip("﻿").rstrip("\n") != "---":
            return None
        for i in range(1, len(self.raw)):
            if self.text(i).rstrip("\n") in ("---", "..."):
                return i
        return len(self.raw) - 1

    def flagged(self, i: int, text: str | None = None) -> bool:
        """Whether line i (or the piece of it shown) holds what may be a credential."""
        if i in self.keys:
            return True
        if text is not None:
            return credential_line(text.rstrip("\n"))
        if i not in self._flagged:
            line = self.text(i).rstrip("\n")
            self._flagged[i] = credential_line(line[:TEXT]) or (
                len(line) > TEXT and credential_line(line[-TEXT:])
            )
        return self._flagged[i]

    def block_before(self, start: int) -> int | None:
        """The indentation of the flagged line whose continuation reaches start, if any:
        the nearest line above with less indentation than every line between."""
        least = None
        for j in range(start - 1, -1, -1):
            if self.blank(j):
                continue
            indent = self.indent(j)
            if least is None or indent < least:
                if self.flagged(j):
                    return indent
                least = indent
                if least == 0:
                    return None
        return None

    def segments(self, start: int, stop: int) -> Iterator[tuple[int, str, int]]:
        """(bytes, text, lines left out) from line start: a run of lines left out as one marker."""
        block = self.block_before(start) if start else None
        run_size = run_n = 0
        run_indent = ""
        i = start
        while i < stop:
            if i == 0 and self.front is not None:
                end = min(self.front, stop - 1)
                yield sum(self.sizes[: end + 1]), FRONT_MATTER + "\n", 0
                i = end + 1
                continue
            hidden = False
            if not self.blank(i):
                indent = self.indent(i)
                if block is not None and indent > block:
                    hidden = True
                elif self.flagged(i):
                    hidden, block = True, indent
                else:
                    block = None
            if hidden:
                if not run_n:
                    text = self.text(i)
                    run_indent = text[: len(text) - len(text.lstrip(" \t"))]
                run_size += self.sizes[i]
                run_n += 1
            else:
                if run_n:
                    yield run_size, run_indent + credentials_marker(run_n) + "\n", run_n
                    run_size = run_n = 0
                yield self.sizes[i], self.text(i), 0
            i += 1
        if run_n:
            end = "\n" if self.ends_line(stop - 1) else ""
            yield run_size, run_indent + credentials_marker(run_n) + end, run_n


def _take(segments, budget: int) -> list[tuple[int, str, int]]:
    taken, chars = [], 0
    for seg in segments:
        if chars + len(seg[1]) > budget:
            break
        taken.append(seg)
        chars += len(seg[1])
    return taken


def _tail_start(text: _Text, floor: int) -> int:
    """The first line, not before floor, from which the lines to the end fit in HALF characters."""
    chars, start = 0, len(text)
    while start > floor and chars + len(text.text(start - 1)) <= HALF:
        start -= 1
        chars += len(text.text(start))
    return start


def _head(text: _Text, stop: int) -> list[tuple[int, str, int]]:
    head = _take(text.segments(0, stop), HALF)
    if not head and stop:
        piece = text.text(0)[:HALF]
        shown = CREDENTIAL if text.flagged(0, piece) else piece
        head = [(size_of(piece, text.encoding), shown, int(shown is CREDENTIAL))]
    return head


def _tail(text: _Text, floor: int) -> list[tuple[int, str, int]]:
    """The lines from the end that fit in HALF characters, not before line floor; none
    fitting: the last line's last HALF characters."""
    if not len(text):
        return []
    start = _tail_start(text, floor)
    if start < len(text):
        tail = list(text.segments(start, len(text)))
        while sum(len(s[1]) for s in tail) > HALF:
            tail.pop(0)
        if tail:
            return tail
    last = len(text) - 1
    if last < floor:
        return []  # the head showed or left out that line already
    piece = text.text(last)[-HALF:]
    block = text.block_before(last)
    # The whole line decides, not only its end: a name cut off from its value
    # (second review of text-as-written, M1)
    hidden = (
        (block is not None and text.indent(last) > block)
        or text.flagged(last)
        or text.flagged(last, piece)
    )
    return [
        (size_of(piece, text.encoding), CREDENTIAL if hidden else piece, int(hidden))
    ]


def _joined(head, tail, size: int) -> str:
    shown = "".join(s[1] for s in head)
    if not shown.endswith("\n"):
        shown += "\n"
    left = size - sum(s[0] for s in head) - sum(s[0] for s in tail)
    return shown + gap(left, "bytes") + "".join(s[1] for s in tail)


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
    text = _Text(data, encoding, complete, front_matter)
    # A text of more than 4 bytes per character of TEXT cannot be whole
    if complete and len(data) <= 4 * TEXT:
        whole = list(text.segments(0, len(text)))
        joined = "".join(s[1] for s in whole)
        if len(joined) <= TEXT:
            return Shown(joined, sum(s[2] for s in whole), True)
    stop = len(text)
    if not complete and stop and not text.ends_line(stop - 1):
        stop -= 1  # cut by the head's end
    head = _head(text, stop)
    if complete:
        end = _tail(text, _lines_in(text, head))
    elif tail is not None and not wide(encoding):
        newline = tail.find(b"\n")
        rest = tail[newline + 1 :] if newline >= 0 else b""
        end = _tail(_Text(rest, encoding, True), 0)
    else:
        end = []
    found = sum(s[2] for s in head) + sum(s[2] for s in end)
    return Shown(_joined(head, end, size), found, False)


def _lines_in(text: _Text, head) -> int:
    """How many lines of text the head's segments cover whole (a front matter or a run of
    lines left out counts its lines; a piece of the first line does not count it, so that
    the tail may show that line's end)."""
    covered, n = 0, 0
    target = sum(s[0] for s in head)
    while n < len(text) and covered + text.sizes[n] <= target:
        covered += text.sizes[n]
        n += 1
    return n


def shown_text(text: str) -> str:
    """A text of ours (a rendering) as head and tail when longer than TEXT, the gap in
    characters; a line longer than HALF cut at a character, at the start and the end."""
    if len(text) <= TEXT:
        return text
    lines = text.splitlines(True)
    head, chars = [], 0
    for line in lines:
        if chars + len(line) > HALF:
            break
        head.append(line)
        chars += len(line)
    if not head:
        head = [lines[0][:HALF]]
    rest = lines[len(head) :] if len(head) < len(lines) and head[0] is lines[0] else []
    tail, chars = [], 0
    for line in reversed(rest):
        if chars + len(line) > HALF:
            break
        tail.insert(0, line)
        chars += len(line)
    if not tail:
        tail = [text[-HALF:]]
    shown = "".join(head)
    left = len(text) - len(shown) - len("".join(tail))
    if not shown.endswith("\n"):
        shown += "\n"
    return shown + gap(left, "characters") + "".join(tail)


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
