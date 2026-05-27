from __future__ import annotations

import asyncio
import os
import sys
import traceback
from typing import TYPE_CHECKING, Any

import keyring
import keyring.backend
import pytest

if TYPE_CHECKING:
    from collections.abc import Generator


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


class DummyKeyring(keyring.backend.KeyringBackend):
    """A minimal in-memory keyring for testing."""

    priority: Any = 10

    def __init__(self) -> None:
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.passwords.pop((service, username), None)


@pytest.fixture(autouse=True)
def mock_keyring() -> DummyKeyring:
    """Mock the keyring backend to avoid NoKeyringError in CI."""
    kb = DummyKeyring()
    keyring.set_keyring(kb)
    return kb


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item: Any, call: Any) -> Generator[None, Any, None]:
    """Dump state when a test fails (including timeouts)."""
    outcome = yield
    report = outcome.get_result()

    if report.when == "call" and report.failed:
        # Check if it's a timeout or other failure we want to debug
        # pytest-timeout raises a signal which might show up in longrepr
        if "timeout" in str(report.longrepr).lower():
            _dump_debug_info()


def _dump_debug_info() -> None:
    print("\n--- DEBUG INFO: HANG DETECTED ---", file=sys.stderr)

    print("\n[Active Threads]", file=sys.stderr)
    for thread_id, stack in sys._current_frames().items():
        print(f"\nThread {thread_id}:", file=sys.stderr)
        traceback.print_stack(stack, file=sys.stderr)

    print("\n[Active Asyncio Tasks]", file=sys.stderr)
    try:
        loop = asyncio.get_running_loop()
        tasks = asyncio.all_tasks(loop)
        for task in tasks:
            print(f"\nTask {task}:", file=sys.stderr)
            task.print_stack(file=sys.stderr)
    except RuntimeError:
        print("No running event loop.", file=sys.stderr)

    print("\n--- END DEBUG INFO ---", file=sys.stderr)


@pytest.fixture(autouse=True)
def cleanup_daemons() -> Generator[None, None, None]:
    """Ensure any orphaned synap daemon processes are killed after each test."""
    yield
    # No-op for now as we use specialized fixtures for daemon tests
    pass
