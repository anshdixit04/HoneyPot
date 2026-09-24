"""Run: cd backend && python3 -m tests.test_log_tailer"""
import asyncio
import os
import tempfile

from app.log_tailer import tail_file


async def demo():
    path = os.path.join(tempfile.mkdtemp(), "cowrie.json")
    with open(path, "w") as f:
        f.write("backlog\n")
    gen = tail_file(path, poll_interval=0.01)

    nxt = asyncio.ensure_future(gen.__anext__())
    await asyncio.sleep(0.05)  # first open: backlog is skipped
    with open(path, "a") as f:
        f.write("a\n")
    assert (await nxt).strip() == "a"

    # Rotate with lines already in the new file before the tailer notices.
    nxt = asyncio.ensure_future(gen.__anext__())
    os.rename(path, path + ".1")
    with open(path, "w") as f:
        f.write("b\nc\n")
    assert (await nxt).strip() == "b"
    assert (await gen.__anext__()).strip() == "c"
    print("ok")


if __name__ == "__main__":
    asyncio.run(asyncio.wait_for(demo(), timeout=3))
