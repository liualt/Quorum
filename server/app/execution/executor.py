"""Executors: run a workspace and return whatever the runner printed.

An executor decides nothing about pass or fail. It reports one of four
statuses — completed, timeout, failed, unavailable — and the caller only
believes results when the status is `completed`.
"""

import asyncio
import logging
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from e2b import AsyncSandbox, CommandExitException, TimeoutException

from app.config import Settings

logger = logging.getLogger(__name__)

TRUNCATION_MARKER = "\n[truncated]"
# What the candidate is told when the sandbox itself failed. The reason is a
# server-side concern and is logged, not shown.
UNAVAILABLE_MESSAGE = "The sandbox was unavailable, so nothing was run."
SANDBOX_DIR = "/home/user/app"
SCRIPT_NAME = "script.json"
# The sandbox has to outlive the command so its own timeout never races ours.
SANDBOX_LIFETIME_MARGIN_SECONDS = 40


@dataclass
class ExecResult:
    status: str  # "completed" | "timeout" | "failed" | "unavailable"
    stdout: str
    stderr: str
    exit_code: int | None
    sandbox_id: str | None
    duration_ms: int


class Executor(Protocol):
    name: str  # "e2b" | "local" | "none"

    async def run(
        self, files: dict[str, str], script: str, *, timeout_s: int, output_cap: int
    ) -> ExecResult: ...


def truncate(text: str, cap: int) -> str:
    data = (text or "").encode("utf-8", "replace")
    if len(data) <= cap:
        return text or ""
    return data[:cap].decode("utf-8", "ignore") + TRUNCATION_MARKER


def classify_sandbox_error(error: Exception) -> tuple[str, str, str, int | None]:
    """Map a failure from the E2B path to (status, stdout, stderr, exit_code).

    A non-zero exit is `completed`: the candidate's code ran, and whether its
    output is usable is `parse_output`'s call. Everything else — a rejected
    key, a rate limit, a transport error — is `unavailable`: nothing about the
    candidate's code was tested, so the run must not read as one that ran and
    broke.
    """
    if isinstance(error, TimeoutException):
        return "timeout", "", str(error), None
    if isinstance(error, CommandExitException):
        return "completed", error.stdout, error.stderr, error.exit_code
    return "unavailable", "", UNAVAILABLE_MESSAGE, None


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


class _BoundedOutput:
    """Collects one output stream, keeping only the first `cap` bytes.

    Everything past the cap is dropped, so a flooding child costs at most
    `cap` bytes of memory however much it writes. `text()` matches
    `truncate`: the kept prefix plus the marker whenever anything was dropped.
    """

    def __init__(self, cap: int):
        self._cap = cap
        self._chunks: list[bytes] = []
        self._size = 0
        self.truncated = False

    def add(self, chunk: bytes | str) -> None:
        data = chunk.encode("utf-8", "replace") if isinstance(chunk, str) else chunk
        room = self._cap - self._size
        if len(data) > room:
            self.truncated = True
            data = data[:max(room, 0)]
        if data:
            self._chunks.append(data)
            self._size += len(data)

    def text(self) -> str:
        data = b"".join(self._chunks)
        if not self.truncated:
            return data.decode("utf-8", "replace")
        return data.decode("utf-8", "ignore") + TRUNCATION_MARKER


def _drain(stream, sink: _BoundedOutput) -> None:
    """Reader-thread body: consume a pipe to EOF so the child never blocks."""
    try:
        for chunk in iter(lambda: stream.read(65536), b""):
            sink.add(chunk)
    finally:
        stream.close()


def _feed(stream, script: str) -> None:
    try:
        stream.write(script.encode("utf-8"))
    except OSError:
        pass  # the child exited without reading; its exit code says so
    finally:
        try:
            stream.close()
        except OSError:
            pass


class _ChildHandle:
    """Lets the asyncio side kill the child that the worker thread owns."""

    def __init__(self):
        self._lock = threading.Lock()
        self._process: subprocess.Popen | None = None
        self._cancelled = False

    def attach(self, process: subprocess.Popen) -> None:
        with self._lock:
            self._process = process
            if self._cancelled:
                _kill_process_group(process)

    def cancel(self) -> None:
        with self._lock:
            self._cancelled = True
            if self._process is not None and self._process.poll() is None:
                _kill_process_group(self._process)


class LocalExecutor:
    """Development and test executor; not the demo path.

    Runs the workspace in a temporary directory with the host interpreter, so
    it offers no isolation beyond the process boundary. The child gets its own
    session and is killed as a group on timeout, because the runner spawns one
    subprocess per check.

    Output is read incrementally and only the first `output_cap` bytes of each
    stream are retained; the rest is drained and discarded so a flooding child
    neither blocks on a full pipe nor grows this process's memory. Cancelling
    the task that awaits `run` kills the process tree straight away rather
    than leaving it to the timeout.
    """

    name = "local"

    async def run(self, files, script, *, timeout_s, output_cap) -> ExecResult:
        child = _ChildHandle()
        try:
            return await asyncio.to_thread(
                self._run_blocking, files, script, timeout_s, output_cap, child
            )
        except asyncio.CancelledError:
            child.cancel()
            raise

    def _run_blocking(self, files, script, timeout_s, output_cap, child=None) -> ExecResult:
        started = time.monotonic()
        workdir = tempfile.mkdtemp(prefix="quorum-run-")
        try:
            _write_workspace(workdir, files)
            process = subprocess.Popen(
                [sys.executable, "runner.py"],
                cwd=workdir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PATH": os.environ.get("PATH", ""),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONIOENCODING": "utf-8",
                    **({"SYSTEMROOT": os.environ["SYSTEMROOT"]} if "SYSTEMROOT" in os.environ else {}),
                },
                start_new_session=True,
            )
            if child is not None:
                child.attach(process)
            stdout, stderr = _BoundedOutput(output_cap), _BoundedOutput(output_cap)
            pumps = [
                threading.Thread(target=_drain, args=(process.stdout, stdout), daemon=True),
                threading.Thread(target=_drain, args=(process.stderr, stderr), daemon=True),
                threading.Thread(target=_feed, args=(process.stdin, script), daemon=True),
            ]
            for pump in pumps:
                pump.start()
            try:
                process.wait(timeout=timeout_s)
                # A non-zero exit is still `completed`: the runner ran, and
                # whether its output is usable is `parse_output`'s call. Same
                # rule as the E2B path.
                status = "completed"
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                _kill_process_group(process)
                process.wait()
                status, exit_code = "timeout", None
            # The pipes reach EOF once every process in the tree is gone, which
            # is why the timeout path has to kill the whole group first.
            for pump in pumps:
                pump.join()
            return ExecResult(
                status=status,
                stdout=_normalize_newlines(stdout.text()),
                stderr=_normalize_newlines(stderr.text()),
                exit_code=exit_code,
                sandbox_id=None,
                duration_ms=_elapsed_ms(started),
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


class E2BExecutor:
    """Sandboxed executor: one throwaway E2B sandbox per run, no network.

    Output arrives through the SDK's stream callbacks and only the first
    `output_cap` bytes of each stream are kept. The SDK's own command handle
    also accumulates every chunk, so once a stream passes the cap the command
    is killed: the result is still `completed` with truncated output and the
    kill's exit code, and nothing past the cap is ever held in memory.
    """

    name = "e2b"

    def __init__(self, api_key: str):
        self._api_key = api_key

    async def run(self, files, script, *, timeout_s, output_cap) -> ExecResult:
        started = time.monotonic()
        sandbox = None
        sandbox_id = None
        stdout, stderr = _BoundedOutput(output_cap), _BoundedOutput(output_cap)
        try:
            sandbox = await AsyncSandbox.create(
                timeout=timeout_s + SANDBOX_LIFETIME_MARGIN_SECONDS,
                secure=True,
                allow_internet_access=False,
                envs={},
                api_key=self._api_key,
            )
            sandbox_id = sandbox.sandbox_id
            for path, content in files.items():
                await sandbox.files.write(f"{SANDBOX_DIR}/{path}", content)
            await sandbox.files.write(f"{SANDBOX_DIR}/{SCRIPT_NAME}", script)

            handle = None
            killed = False

            async def _flooded() -> None:
                nonlocal killed
                if killed or handle is None:
                    return
                killed = True
                try:
                    await handle.kill()
                except Exception:  # the command timeout still bounds it
                    logger.warning("could not kill flooding command in %s", sandbox_id, exc_info=True)

            async def on_stdout(chunk: str) -> None:
                stdout.add(chunk)
                if stdout.truncated:
                    await _flooded()

            async def on_stderr(chunk: str) -> None:
                stderr.add(chunk)
                if stderr.truncated:
                    await _flooded()

            # commands.run takes no stdin content, so the script is a file.
            handle = await sandbox.commands.run(
                f"python3 runner.py < {SCRIPT_NAME}",
                cwd=SANDBOX_DIR,
                timeout=timeout_s,
                background=True,
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )
            try:
                exit_code = (await handle.wait()).exit_code
            except CommandExitException as error:
                exit_code = error.exit_code
            return ExecResult(
                status="completed",
                stdout=stdout.text(),
                stderr=stderr.text(),
                exit_code=exit_code,
                sandbox_id=sandbox_id,
                duration_ms=_elapsed_ms(started),
            )
        except Exception as error:
            status, out, err, exit_code = classify_sandbox_error(error)
            if status == "unavailable":
                logger.exception("E2B run failed before any results were produced")
            return ExecResult(
                status=status,
                stdout=truncate(out, output_cap),
                stderr=truncate(err, output_cap),
                exit_code=exit_code,
                sandbox_id=sandbox_id,
                duration_ms=_elapsed_ms(started),
            )
        finally:
            if sandbox is not None:
                try:
                    await sandbox.kill()
                except Exception:  # a leaked sandbox expires on its own timeout
                    logger.warning("could not kill sandbox %s", sandbox_id, exc_info=True)


class UnavailableExecutor:
    """Stands in when no executor is configured, so runs fail honestly."""

    name = "none"

    def __init__(self, reason: str = "no sandbox executor is configured"):
        self._reason = reason

    async def run(self, files, script, *, timeout_s, output_cap) -> ExecResult:
        return ExecResult(
            status="unavailable",
            stdout="",
            stderr=self._reason,
            exit_code=None,
            sandbox_id=None,
            duration_ms=0,
        )


def build_executor(settings: Settings) -> Executor:
    if settings.EXECUTOR == "local":
        return LocalExecutor()
    if settings.EXECUTOR == "e2b" and settings.E2B_API_KEY:
        return E2BExecutor(settings.E2B_API_KEY)
    if settings.EXECUTOR == "e2b":
        return UnavailableExecutor("E2B_API_KEY is not set")
    return UnavailableExecutor(f"unknown executor: {settings.EXECUTOR}")


def _normalize_newlines(text: str) -> str:
    """What the old text-mode pipes did: the child's os.linesep reads as LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_workspace(workdir: str, files: dict[str, str]) -> None:
    for path, content in files.items():
        target = os.path.join(workdir, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)


def _kill_process_group(process: subprocess.Popen) -> None:
    if os.name == "nt":
        # Killing only the wrapper leaves check children holding its pipes open.
        subprocess.run(
            [os.path.join(os.environ["SYSTEMROOT"], "System32", "taskkill.exe"),
             "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.poll() is None:
            process.kill()
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        process.kill()
