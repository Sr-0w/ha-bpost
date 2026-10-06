"""Build the self-contained HACS release without modifying the checkout.

HACS extracts this archive directly into config/custom_components/my_bpost/.
Only runtime sources, translations, the frontend and the license are included.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import tomllib
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def build_release(output: Path, *, root: Path = ROOT, tag: str | None = None) -> str:
    integration = root / "custom_components/my_bpost"
    client = root / "pybpost/pybpost"
    version = json.loads((integration / "manifest.json").read_text())["version"]
    client_version = tomllib.loads((root / "pybpost/pyproject.toml").read_text())["project"]["version"]
    declared = re.search(r'__version__\s*=\s*[\"\']([^\"\']+)', (client / "__init__.py").read_text())
    if not re.fullmatch(r"\d+\.\d+\.\d+(?:b[1-9]\d*)?", version):
        raise ValueError("Release version must be major.minor.patch, optionally followed by bN")
    if client_version != version or declared is None or declared[1] != version:
        raise ValueError("Integration and client versions must match")
    if tag is not None and tag.removeprefix("v") != version:
        raise ValueError("Release tag does not match the manifest version")
    key_source = (client / "const.py").read_text()
    key = re.search(r'X_API_KEY = "([^\"]+)"', key_source)
    if "REPLACE_ME" in key_source or key is None or len(key[1]) != 40:
        raise ValueError("Missing embedded generic client key")

    files = {p.name: p for p in integration.glob("*.py")}
    files["manifest.json"] = integration / "manifest.json"
    files["strings.json"] = integration / "strings.json"
    files["services.yaml"] = integration / "services.yaml"
    for folder, pattern in (("translations", "*.json"), ("frontend", "*.js"), ("brand", "*.png")):
        files.update({f"{folder}/{p.name}": p for p in (integration / folder).glob(pattern)})
    files.update({f"pybpost/{p.name}": p for p in client.glob("*.py")})
    files["LICENSE"] = root / "LICENSE"
    for name, path in files.items():
        if path.is_symlink():
            raise ValueError(f"Release input must not be a symlink: {name}")
    # Stable ordering, timestamps and modes make identical input reproducible.
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, path in sorted(files.items()):
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes())
    return version


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "bpost.zip")
    parser.add_argument("--tag")
    args = parser.parse_args()
    version = build_release(args.output, tag=args.tag)
    print(f"Built My bpost {version}: {args.output}")
