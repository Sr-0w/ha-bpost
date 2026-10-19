"""Check that a GitHub release tag matches the self-contained integration.

HACS installs ``custom_components/my_bpost`` from the tagged commit. The client
already lives in that directory, so this script does not build an archive.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def check_release(*, root: Path = ROOT, tag: str | None = None) -> str:
    integration = root / "custom_components/my_bpost"
    client = integration / "pybpost"
    version = json.loads((integration / "manifest.json").read_text())["version"]
    client_version = tomllib.loads((root / "pybpost/pyproject.toml").read_text())["project"]["version"]
    declared = re.search(r'__version__\s*=\s*["\']([^"\']+)', (client / "__init__.py").read_text())
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:b[1-9]\d*)?", version):
        raise ValueError("Release version must be major.minor.patch, optionally followed by bN")
    if client_version != version or declared is None or declared[1] != version:
        raise ValueError("Integration and client versions must match")
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError("Release tag does not match the manifest version")
    hacs = json.loads((root / "hacs.json").read_text())
    if "filename" in hacs or hacs.get("zip_release"):
        raise ValueError("HACS must install the tagged integration, not a separate zip")
    if client.is_symlink() or not (client / "client.py").is_file():
        raise ValueError("The client must be committed inside the integration")
    link = root / "pybpost/pybpost"
    if not link.is_symlink() or link.resolve() != client.resolve():
        raise ValueError("The standalone package must link to the integration client")
    for path in client.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Integration file must not be a symlink: {path.relative_to(integration)}")
    key_source = (client / "const.py").read_text()
    key = re.search(r'X_API_KEY = "([^"]+)"', key_source)
    if "REPLACE_ME" in key_source or key is None or len(key[1]) != 40:
        raise ValueError("Missing embedded generic client key")
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    version = check_release(tag=args.tag)
    print(f"My bpost {version} is a self-contained tagged integration")
