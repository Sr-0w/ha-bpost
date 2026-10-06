"""Run each full HA bootstrap in its own process, as Home Assistant expects."""

import asyncio
from functools import wraps
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from zipfile import ZipFile
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
    """Exercise the release artifact with HACS's integration extraction layout.

    CI passes the very archive it built; local runs use the same build script.
    No editable client installation or source-copy fallback is used.
    """
    source = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as staging:
        supplied = os.environ.get("BPOST_RELEASE_ZIP")
        archive = Path(supplied) if supplied else Path(staging) / "bpost.zip"
        if not supplied:
            subprocess.run([sys.executable, str(source / "scripts/build_release.py"),
                            "--output", str(archive)], check=True, capture_output=True)
        with ZipFile(archive) as package:
            assert "manifest.json" in package.namelist()
            assert "pybpost/client.py" in package.namelist()
            package.extractall(config_dir / "custom_components/my_bpost")


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
