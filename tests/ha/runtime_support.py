"""Run each full HA bootstrap in its own process, as Home Assistant expects."""

import asyncio
from functools import wraps
import os
from pathlib import Path
import shutil
import sys
from unittest.mock import AsyncMock, patch


async def assert_coordinators_stopped(test, parent):
    """Native entry unload must stop even the permanently subscribed pollers."""
    for coordinator in (parent, parent.live, parent.mail):
        test.assertTrue(coordinator._shutdown_requested)
        test.assertIsNone(coordinator._unsub_refresh)
        test.assertFalse(coordinator._listeners)
        with patch.object(coordinator, '_async_update_data', new=AsyncMock()) as fetch:
            await coordinator.async_refresh()
            fetch.assert_not_awaited()


def install_release(config_dir: Path) -> None:
    """Install the integration the way HACS copies a tagged source tree.

    The client is committed inside the integration, so no release archive is built.
    """
    source = Path(__file__).resolve().parents[2] / "custom_components" / "my_bpost"
    destination = config_dir / "custom_components" / "my_bpost"
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    client = destination / "pybpost" / "client.py"
    assert (destination / "manifest.json").is_file()
    assert client.is_file() and not client.is_symlink()


def isolated_runtime(test):
    """Keep real process-global HA/DNS instrumentation isolated between cases.

    The child runs the original test, including every assertion and entry reload.
    Only the full bootstrap cases need this; entry/automation tests stay in-process.
    """
    @wraps(test)
    async def run(self):
        if os.environ.get('BPOST_RUNTIME_TEST_CHILD') == test.__module__:
            return await test(self)
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'unittest', 'discover',
            '-s', str(Path(__file__).parent), '-p', f'{test.__module__}.py', '-v',
            env={**os.environ, 'BPOST_RUNTIME_TEST_CHILD': test.__module__},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 60)
            self.assertEqual(process.returncode, 0, output.decode(errors='replace'))
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    return run
