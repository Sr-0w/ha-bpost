"""Run official HACS validators against local files and live GitHub metadata.

Requires a separate HACS source checkout with its Python/frontend dependencies.
This does not publish changes or run the GitHub Action. It also exercises HACS's
real ZIP extractor, substituting only the release download with the local ZIP.
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from zipfile import ZipFile

import aiohttp
from homeassistant.core import HomeAssistant

ROOT = Path(__file__).resolve().parents[1]


async def validate(hacs_source: Path, archive: Path) -> None:
    sys.path.insert(0, str(hacs_source.resolve()))
    from custom_components.hacs.base import HacsBase
    from custom_components.hacs.repositories.base import HacsManifest
    from custom_components.hacs.repositories.integration import HacsIntegrationRepository
    from custom_components.hacs.utils.validate import Validate
    from custom_components.hacs.validate.manager import ValidationManager

    logging.basicConfig(level=logging.INFO)
    with tempfile.TemporaryDirectory() as temp:
        hass = HomeAssistant(temp)
        try:
            async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=30)) as session:
                async with session.get("https://api.github.com/repos/Sr-0w/ha-bpost") as response:
                    response.raise_for_status()
                    metadata = await response.json()
                hacs = HacsBase()
                hacs.hass = hass
                hacs.core.config_path = temp
                hacs.system.action = True
                hacs.session = session
                repo = HacsIntegrationRepository(hacs, "Sr-0w/ha-bpost")
                repo.data.update_data(metadata, action=True)
                repo.data.domain = "my_bpost"
                repo.ref = "local-workspace"
                repo.content.path.remote = "custom_components/my_bpost"
                repo.content.path.local = repo.localpath
                repo.repository_object = SimpleNamespace(attributes=metadata)
                names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                                                cwd=ROOT, text=True).splitlines()
                repo.treefiles = names
                repo.tree = [SimpleNamespace(filename=Path(name).name, full_path=name) for name in names]
                manifest = json.loads((ROOT / "hacs.json").read_text())
                repo.repository_manifest = HacsManifest.from_dict(manifest)

                async def local_hacs_json(**kwargs):
                    return manifest

                async def local_integration_manifest(**kwargs):
                    return json.loads((ROOT / "custom_components/my_bpost/manifest.json").read_text())

                repo.get_hacs_json_raw = local_hacs_json
                repo.get_integration_manifest = local_integration_manifest
                manager = ValidationManager(hacs, hass)
                await manager.async_load(repo)
                checks = [item for item in manager.validators if not item.categories or repo.data.category in item.categories]
                for check in checks:
                    await check.execute_validation()
                failed = [item.slug for item in checks if item.failed]
                if failed:
                    raise RuntimeError(f"HACS validation failed: {', '.join(failed)}")
                print(f"PASS: {len(checks)} official HACS validators (local files + live repository metadata)")

                payload = archive.read_bytes()

                async def local_download(url, **kwargs):
                    return payload

                async def save_file(filename, content):
                    await hass.async_add_executor_job(Path(filename).write_bytes, content)
                    return True

                hacs.async_download_file = local_download
                hacs.async_save_file = save_file
                outcome = Validate()
                await repo.async_download_zip_file({"name": "bpost.zip", "url": "local-release-artifact"}, outcome)
                if not outcome.success:
                    raise RuntimeError(f"HACS extraction failed: {outcome.errors}")
                destination = Path(repo.localpath)
                with ZipFile(archive) as package:
                    for name in package.namelist():
                        assert (destination / name).read_bytes() == package.read(name), name
                assert (destination / "manifest.json").is_file()
                assert (destination / "pybpost/client.py").is_file()
                assert not (destination / "custom_components").exists()
                print("PASS: official HACS ZIP extraction, runtime files and bundled client")
        finally:
            await hass.async_stop(force=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hacs-source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(validate(args.hacs_source, args.archive))
