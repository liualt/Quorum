"""Executor selection, output capping, and the E2B error mapping.

The E2B path needs an API key and a network, so only its pure pieces are
exercised here; the local executor covers the end-to-end behaviour.
"""

import pytest
from e2b import (
    AuthenticationException,
    CommandExitException,
    RateLimitException,
    SandboxException,
    TimeoutException,
)

from app.config import Settings
from app.execution.executor import (
    TRUNCATION_MARKER,
    UNAVAILABLE_MESSAGE,
    E2BExecutor,
    LocalExecutor,
    UnavailableExecutor,
    build_executor,
    classify_sandbox_error,
    truncate,
)


def test_build_executor_returns_the_local_executor(settings):
    executor = build_executor(settings)

    assert isinstance(executor, LocalExecutor)
    assert executor.name == "local"


def test_build_executor_returns_e2b_when_a_key_is_configured():
    executor = build_executor(Settings(EXECUTOR="e2b", E2B_API_KEY="secret"))

    assert isinstance(executor, E2BExecutor)
    assert executor.name == "e2b"


def test_build_executor_falls_back_to_unavailable_without_a_key():
    executor = build_executor(Settings(EXECUTOR="e2b", E2B_API_KEY=""))

    assert isinstance(executor, UnavailableExecutor)
    assert executor.name == "none"


async def test_unavailable_executor_reports_unavailable():
    result = await UnavailableExecutor().run({}, "{}", timeout_s=1, output_cap=100)

    assert result.status == "unavailable"
    assert result.stdout == ""
    assert result.exit_code is None
    assert result.sandbox_id is None


def test_truncate_leaves_short_output_alone():
    assert truncate("hello", 100) == "hello"


def test_truncate_marks_what_it_cut():
    truncated = truncate("y" * 500, 100)

    assert truncated == "y" * 100 + TRUNCATION_MARKER


async def test_local_executor_caps_output():
    files = {"runner.py": "import sys\nsys.stdin.read()\nprint('y' * 5000)\n"}

    result = await LocalExecutor().run(files, "{}", timeout_s=20, output_cap=100)

    assert result.status == "completed"
    assert result.stdout.endswith(TRUNCATION_MARKER)
    assert len(result.stdout) == 100 + len(TRUNCATION_MARKER)


async def test_local_executor_reports_a_non_zero_exit_as_completed():
    """The runner ran, so the exit code does not decide: `parse_output` does.

    Same rule as the E2B path, so a run's status means one thing whichever
    executor produced it.
    """
    files = {"runner.py": "import sys\nsys.stdin.read()\nsys.stderr.write('nope')\nsys.exit(3)\n"}

    result = await LocalExecutor().run(files, "{}", timeout_s=20, output_cap=1000)

    assert result.status == "completed"
    assert result.exit_code == 3
    assert result.stderr == "nope"


async def test_local_executor_writes_nested_workspace_files():
    files = {
        "fixtures/users.json": '{"users": []}',
        "runner.py": "import sys\nsys.stdin.read()\nprint(open('fixtures/users.json').read())\n",
    }

    result = await LocalExecutor().run(files, "{}", timeout_s=20, output_cap=1000)

    assert result.status == "completed"
    assert result.stdout.strip() == '{"users": []}'


async def test_local_executor_timeout_kills_children_holding_output_pipes():
    files = {"runner.py": (
        "import subprocess, sys, time\n"
        "sys.stdin.read()\n"
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "print('started', flush=True)\n"
        "time.sleep(30)\n"
    )}
    result = await LocalExecutor().run(files, "{}", timeout_s=1, output_cap=1000)

    assert result.status == "timeout"
    assert result.exit_code is None
    assert "started" in result.stdout
    assert result.duration_ms < 10_000


async def test_local_executor_preserves_unicode_output():
    files = {"runner.py": "import sys\nsys.stdin.read()\nprint('caf\\u00e9 \\u4f60\\u597d')\n"}
    result = await LocalExecutor().run(files, "{}", timeout_s=20, output_cap=1000)

    assert result.status == "completed"
    assert result.stdout.strip() == "café 你好"


def test_local_executor_is_labelled_as_the_development_executor():
    assert "Development and test executor" in LocalExecutor.__doc__


@pytest.mark.parametrize(
    "error",
    [
        SandboxException("boom"),
        AuthenticationException("nope"),
        RateLimitException("slow down"),
        RuntimeError("some httpx transport failure"),
    ],
)
def test_classify_sandbox_error_reports_infrastructure_failures_as_unavailable(error):
    status, stdout, stderr, exit_code = classify_sandbox_error(error)

    assert status == "unavailable"
    assert stdout == ""
    assert exit_code is None
    # The candidate is told the sandbox failed, not how.
    assert stderr == UNAVAILABLE_MESSAGE


def test_classify_sandbox_error_maps_a_sandbox_timeout():
    status, _stdout, _stderr, exit_code = classify_sandbox_error(TimeoutException("too slow"))

    assert status == "timeout"
    assert exit_code is None


def test_classify_sandbox_error_keeps_output_from_a_command_that_ran():
    error = CommandExitException(stderr="bad", stdout="partial", exit_code=1, error=None)

    assert classify_sandbox_error(error) == ("completed", "partial", "bad", 1)


FLOOD_BYTES = 5 * 1024 * 1024


def _flood_runner(stream: str) -> dict[str, str]:
    other = "stderr" if stream == "stdout" else "stdout"
    return {"runner.py": (
        "import sys\n"
        "sys.stdin.read()\n"
        "chunk = b'x' * 65536\n"
        f"for _ in range({FLOOD_BYTES} // len(chunk)):\n"
        f"    sys.{stream}.buffer.write(chunk)\n"
        f"sys.{stream}.buffer.flush()\n"
        f"print('done', file=sys.{other})\n"
    )}


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
async def test_local_executor_bounds_a_flooding_stream_at_source(stream):
    """5 MB on one pipe: the child finishes, memory stays at the cap, and the
    other stream still carries what the child said after the flood."""
    cap = 4096
    result = await LocalExecutor().run(_flood_runner(stream), "{}", timeout_s=20, output_cap=cap)

    assert result.status == "completed"
    assert result.exit_code == 0
    flooded = getattr(result, stream)
    other = getattr(result, "stderr" if stream == "stdout" else "stdout")
    assert flooded == "x" * cap + TRUNCATION_MARKER
    assert other.strip() == "done"
    assert result.duration_ms < 10_000


async def test_local_executor_keeps_the_head_of_a_flood_that_times_out():
    files = {"runner.py": (
        "import sys, time\n"
        "sys.stdin.read()\n"
        "print('head', flush=True)\n"
        "while True:\n"
        "    sys.stdout.buffer.write(b'y' * 65536)\n"
        "    sys.stdout.buffer.flush()\n"
    )}
    result = await LocalExecutor().run(files, "{}", timeout_s=1, output_cap=200)

    assert result.status == "timeout"
    assert result.stdout.startswith("head")
    assert result.stdout.endswith(TRUNCATION_MARKER)
    assert len(result.stdout.encode()) <= 200 + len(TRUNCATION_MARKER)
    assert result.duration_ms < 10_000


def _pid_alive(pid: int) -> bool:
    import os
    import subprocess

    if os.name == "nt":
        listing = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True
        ).stdout
        return str(pid) in listing
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_cancelling_the_local_executor_kills_the_child_promptly(tmp_path):
    """A06: cancellation must not leave the child to the execution timeout."""
    import asyncio
    import time

    pid_file = tmp_path / "pid"
    files = {"runner.py": (
        "import os, sys, time\n"
        "sys.stdin.read()\n"
        f"open({str(pid_file)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\n"
    )}
    task = asyncio.create_task(LocalExecutor().run(files, "{}", timeout_s=60, output_cap=100))
    deadline = time.monotonic() + 10
    while not pid_file.exists() and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    pid = int(pid_file.read_text())
    assert _pid_alive(pid)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    deadline = time.monotonic() + 2
    while _pid_alive(pid) and time.monotonic() < deadline:
        await asyncio.sleep(0.05)
    assert not _pid_alive(pid)


class _FakeHandle:
    def __init__(self, chunks: list[str], on_stdout, on_stderr):
        self._chunks, self._on_stdout, self._on_stderr = chunks, on_stdout, on_stderr
        self.killed = False

    async def kill(self) -> bool:
        self.killed = True
        return True

    async def wait(self):
        for chunk in self._chunks:
            if self.killed:
                break
            await self._on_stdout(chunk)
        if self.killed:
            raise CommandExitException(stdout="".join(self._chunks), stderr="", exit_code=137, error=None)
        from e2b import CommandResult

        return CommandResult(stdout="".join(self._chunks), stderr="", exit_code=0, error=None)


class _FakeSandbox:
    """Enough of AsyncSandbox for the executor's callback wiring."""

    chunks: list[str] = []
    handles: list[_FakeHandle] = []
    sandbox_id = "sbx-fake"

    def __init__(self):
        outer = self

        class _Files:
            async def write(self, path, content):
                pass

        class _Commands:
            async def run(self, cmd, **kwargs):
                handle = _FakeHandle(outer.chunks, kwargs["on_stdout"], kwargs["on_stderr"])
                outer.handles.append(handle)
                return handle

        self.files, self.commands = _Files(), _Commands()

    @classmethod
    async def create(cls, **kwargs):
        return cls()

    async def kill(self):
        pass


async def test_e2b_executor_keeps_the_cap_and_kills_a_flooding_command(monkeypatch):
    import app.execution.executor as module

    _FakeSandbox.chunks = ["z" * 1000] * 50
    _FakeSandbox.handles = []
    monkeypatch.setattr(module, "AsyncSandbox", _FakeSandbox)

    result = await E2BExecutor("key").run({"runner.py": ""}, "{}", timeout_s=5, output_cap=2500)

    assert result.status == "completed"
    assert result.stdout == "z" * 2500 + TRUNCATION_MARKER
    assert result.exit_code == 137
    assert result.sandbox_id == "sbx-fake"
    handle = _FakeSandbox.handles[0]
    assert handle.killed


async def test_e2b_executor_passes_bounded_output_through_unchanged(monkeypatch):
    import app.execution.executor as module

    _FakeSandbox.chunks = ['{"results": []}\n']
    _FakeSandbox.handles = []
    monkeypatch.setattr(module, "AsyncSandbox", _FakeSandbox)

    result = await E2BExecutor("key").run({"runner.py": ""}, "{}", timeout_s=5, output_cap=2500)

    assert result.status == "completed"
    assert result.stdout == '{"results": []}\n'
    assert result.exit_code == 0
    assert not _FakeSandbox.handles[0].killed
