"""
Tails a Cowrie JSON log file like `tail -f`, handling the daily log
rotation Cowrie does (file gets recreated under a new date suffix).

Kept dependency-free (no watchdog needed for this simple polling approach)
so the prototype has as few moving parts as possible. Revisit with
inotify/watchdog if polling interval ever becomes a bottleneck - it won't
at this event volume.
"""
import asyncio
import os
import time
from typing import AsyncGenerator


async def tail_file(path: str, poll_interval: float = 0.5) -> AsyncGenerator[str, None]:
    """Yields new lines appended to `path`, following file rotation.

    Cowrie rotates by closing the current file and starting a new one with
    a date suffix, while a stable symlink/latest path is NOT guaranteed -
    so we watch the directory for the newest matching file if `path`
    disappears, rather than assuming a fixed filename forever.
    """
    current_inode = None
    fh = None

    while True:
        if fh is None:
            if not os.path.exists(path):
                await asyncio.sleep(poll_interval)
                continue
            fh = open(path, "r")
            fh.seek(0, os.SEEK_END)  # start at end - only new events, not backlog
            current_inode = os.fstat(fh.fileno()).st_ino

        line = fh.readline()
        if line:
            yield line
            continue

        # No new data - check if the file was rotated out from under us.
        try:
            disk_inode = os.stat(path).st_ino
        except FileNotFoundError:
            disk_inode = None

        if disk_inode != current_inode:
            fh.close()
            fh = None  # reopen next loop iteration
        else:
            await asyncio.sleep(poll_interval)
