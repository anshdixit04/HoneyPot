"""
Parses Cowrie's raw per-session ttylog recordings and turns them into
the guided "inject the next command" data the dashboard's replay UI
uses (see docs/02-design-doc.md section 9).

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
import logging
import os
import re
import struct
import time
from typing import Optional

logger = logging.getLogger("honeypot-backend")

OP_CLOSE = 2
OP_WRITE = 3

# Cowrie's shell wraps each prompt-and-echo cycle in IRM (insert mode)
# ANSI codes: \x1b[4h right before showing the prompt, \x1b[4l right
# after the typed line is echoed back and before the command's output
# starts. This is a reliable, content-independent way to find command
# boundaries — it doesn't depend on knowing the fake hostname/prompt
# string, which varies per session.
IRM_ON = "\x1b[4h"
IRM_OFF = "\x1b[4l"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

TTYLOG_DIR = os.environ.get(
    "TTYLOG_DIR",
    os.path.join(os.path.dirname(__file__), "..", "..", "data", "cowrie-tty"),
)

_HEADER_FMT = "<iLiiLL"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)

_MAX_STEPS = 100


def ttylog_path(filename: str) -> str:
    return os.path.join(TTYLOG_DIR, filename)


def ttylog_exists(filename: str) -> bool:
    return os.path.isfile(ttylog_path(filename))


def _parse_frames(filename: str) -> Optional[list[tuple[float, str]]]:
    """Reads a ttylog file into (relative_seconds, text) frames — only
    the direction the session's first OP_WRITE used (in practice the
    shell's own output stream, which is what a viewer should see — see
    the module docstring above). Returns None if missing/empty."""
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

    return frames or None


def build_asciicast(filename: str) -> Optional[str]:
    """Returns the session recording as newline-delimited asciicast v2
    text (a header JSON line followed by one `[time, "o", text]` JSON
    array per frame). Kept for API completeness / possible reuse; the
    dashboard itself uses build_command_steps() for the guided injector
    UI instead (docs/02-design-doc.md section 9)."""
    frames = _parse_frames(filename)
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


def _clean(text: str) -> str:
    return _ANSI_RE.sub("", text)


def build_command_steps(filename: str) -> Optional[dict]:
    """Groups a ttylog's frames into a `{banner, steps}` structure — one
    step per command, each `{prompt, command, output}` — instead of a
    raw timed playback. This is what drives the guided "inject the next
    command" UI: the frontend reveals one step at a time on request,
    rather than auto-playing the whole thing.

    Cowrie logs character-by-character for interactive sessions (real
    attacker keystrokes, not line-buffered), so naively treating each
    raw frame as a "step" would mean dozens of single-character reveals
    per command. Grouping by the IRM_ON/IRM_OFF markers (see module
    top) instead gives one step per actual command.
    """
    frames = _parse_frames(filename)
    if not frames:
        return None

    texts = [t for _, t in frames]
    n = len(texts)

    first_on = next((i for i, t in enumerate(texts) if IRM_ON in t), None)
    if first_on is None:
        # No command cycles at all (e.g. connection closed before any
        # input) — just the initial banner/output, no steps.
        return {"banner": _clean("".join(texts)), "steps": []}

    banner = _clean("".join(texts[:first_on]))
    steps = []
    i = first_on

    while i < n and len(steps) < _MAX_STEPS:
        # This frame contains IRM_ON; the prompt text is whatever
        # follows it in the same frame, or the next frame if IRM_ON
        # was delivered on its own.
        prompt_part = texts[i].split(IRM_ON, 1)[1]
        i += 1
        if not prompt_part and i < n:
            prompt_part = texts[i]
            i += 1
        prompt = _clean(prompt_part)

        # Typed-command echo: character frames up to and including the
        # one that completes the line, stopping early if we somehow
        # hit another IRM_ON first (shouldn't happen, but don't hang).
        command_parts = []
        while i < n and IRM_ON not in texts[i]:
            command_parts.append(texts[i])
            ended_line = "\r\n" in texts[i]
            i += 1
            if ended_line:
                break
        command = _clean("".join(command_parts)).strip()

        if i < n and IRM_OFF in texts[i]:
            i += 1

        output_parts = []
        while i < n and IRM_ON not in texts[i]:
            output_parts.append(texts[i])
            i += 1
        output = _clean("".join(output_parts))

        if command or output.strip():
            steps.append({"prompt": prompt, "command": command, "output": output})

    return {"banner": banner, "steps": steps}


def prune_old_ttylogs(days: int) -> int:
    """Deletes ttylog files last modified more than `days` ago. Ttylogs
    are binary and accumulate forever otherwise (see docs/02-design-doc.md
    section 9.5). Returns the number of files deleted; never raises —
    called from a background loop that should keep running even if one
    file can't be removed."""
    if not os.path.isdir(TTYLOG_DIR):
        return 0

    cutoff = time.time() - days * 86400
    deleted = 0
    for name in os.listdir(TTYLOG_DIR):
        path = os.path.join(TTYLOG_DIR, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted += 1
        except OSError as exc:
            logger.warning("Could not prune ttylog %s: %s", name, exc)
    return deleted
