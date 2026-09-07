"""Executor selection, output capping, and the E2B error mapping.

The E2B path needs an API key and a network, so only its pure pieces are
exercised here; the local executor covers the end-to-end behaviour.
"""

import pytest
from e2b import (
    AuthenticationException,
    CommandExitException,
    SandboxException,
    TimeoutException,
)

from app.config import Settings
from app.execution.executor import (
    TRUNCATION_MARKER,
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


async def test_local_executor_reports_a_non_zero_exit_as_failed():
    files = {"runner.py": "import sys\nsys.stdin.read()\nsys.stderr.write('nope')\nsys.exit(3)\n"}

    result = await LocalExecutor().run(files, "{}", timeout_s=20, output_cap=1000)

    assert result.status == "failed"
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


def test_local_executor_is_labelled_as_the_development_executor():
    assert "Development and test executor" in LocalExecutor.__doc__


@pytest.mark.parametrize(
    "error,expected",
    [
        (TimeoutException("too slow"), "timeout"),
        (SandboxException("boom"), "failed"),
    ],
)
def test_classify_sandbox_error_maps_status(error, expected):
    status, _stdout, _stderr, exit_code = classify_sandbox_error(error)

    assert status == expected
    assert exit_code is None


def test_classify_sandbox_error_keeps_command_output():
    error = CommandExitException(stderr="bad", stdout="partial", exit_code=1, error=None)

    assert classify_sandbox_error(error) == ("failed", "partial", "bad", 1)


def test_classify_sandbox_error_treats_a_rejected_key_as_unavailable():
    status, _stdout, _stderr, _exit_code = classify_sandbox_error(AuthenticationException("nope"))

    assert status == "unavailable"
