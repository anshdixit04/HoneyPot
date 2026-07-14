"""
Converts Cowrie's raw per-session ttylog recordings into asciicast v2
text, playable by asciinema-player in the frontend (see
docs/02-design-doc.md section 9).

Cowrie's ttylog frame format (ported from Cowrie's own
src/cowrie/scripts/asciinema.py, the source of truth for this format):
each frame is a 24-byte little-endian header `<iLiiLL` -- (op, tty,
length, direction, sec, usec) -- followed by `length` bytes of raw
payload. Only OP_WRITE frames matching the session's "preferred
direction" (whichever direction the first write used — in practice the
fake shell's own output stream, since that's what a viewer should see,
same as how asciinema itself only records stdout) are kept; OP_CLOSE
ends the session.
"""
import json
import os
import struct
from typing import Optional

OP_CLOSE = 2
OP_WRITE = 3

TTYLOG_DIR = os.environ.get(
    "TTYLOG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "cowrie-tty"),
)

_HEADER_FMT = "<iLiiLL"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)


def ttylog_path(filename: str) -> str:
    return os.path.join(TTYLOG_DIR, filename)


def ttylog_exists(filename: str) -> bool:
    return os.path.isfile(ttylog_path(filename))


def build_asciicast(filename: str) -> Optional[str]:
    """Returns the session recording as newline-delimited asciicast v2
    text (a header JSON line followed by one `[time, "o", text]` JSON
    array per output frame), or None if the file is missing/unparseable/
    empty."""
    path = ttylog_path(filename)
    if not os.path.isfile(path):
        return None

    frames: list[tuple[float, str]] = []
    currtty = None
    prefdir = None
    t0 = None

    with open(path, "rb") as fd:
        while True:
            header = fd.read(_HEADER_SIZE)
            if len(header) < _HEADER_SIZE:
                break
            op, tty, length, direction, sec, usec = struct.unpack(_HEADER_FMT, header)
            data = fd.read(length)
            if len(data) < length:
                break

            if currtty is None:
                currtty = tty
            if tty != currtty:
                continue
            if op == OP_CLOSE:
                break
            if op != OP_WRITE:
                continue

            if prefdir is None:
                prefdir = direction
            if direction != prefdir:
                continue

            t = sec + usec / 1_000_000
            if t0 is None:
                t0 = t
            text = data.replace(b"\n", b"\r\n").decode("utf-8", errors="replace")
            frames.append((t - t0, text))

    if not frames:
        return None

    header_line = json.dumps(
        {
            "version": 2,
            "width": 80,
            "height": 24,
            "title": "Honeypot Session Replay",
            "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"},
        }
    )
    lines = [header_line]
    lines.extend(json.dumps([round(t, 6), "o", text]) for t, text in frames)
    return "\n".join(lines) + "\n"
