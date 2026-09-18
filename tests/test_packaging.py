"""Packaging guards for the ha-bpost repository (stdlib only).

Run:  python3 -m unittest discover -s tests -v

These tests protect the HACS distribution contract:
- the bpost client key must NEVER be committed to source (it is injected
  from a GitHub secret when the release asset is built);
- manifest.json / hacs.json keep the metadata HACS and Home Assistant require;
- shipped JSON files stay valid.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / "bpost"


class SourceHygieneTest(unittest.TestCase):
    def test_no_api_key_in_source(self):
        """The x-api-key placeholder must survive in source (never the key)."""
        const = ROOT / "pybpost" / "pybpost" / "const.py"
        text = const.read_text(encoding="utf-8")
        self.assertIn('X_API_KEY = "REPLACE_ME_AT_DEPLOY_TIME"', text)

    def test_no_vendored_copy_in_source(self):
        """pybpost is vendored at release time, not committed twice."""
        self.assertFalse((INTEGRATION / "pybpost").exists())

    def test_no_bytecode_committed(self):
        import subprocess

        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        bad = [line for line in out.stdout.splitlines()
               if "__pycache__" in line or line.endswith((".pyc", ".pyo"))]
        self.assertEqual(bad, [])


class ManifestTest(unittest.TestCase):
    def test_required_keys(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        for key in (
            "domain",
            "name",
            "version",
            "documentation",
            "issue_tracker",
            "codeowners",
            "config_flow",
            "iot_class",
        ):
            self.assertIn(key, manifest, f"missing manifest key: {key}")
        self.assertEqual(manifest["domain"], "bpost")
        self.assertTrue(manifest["config_flow"])

    def test_version_format(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+$")

    def test_repo_urls_point_at_ha_bpost(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        for key in ("documentation", "issue_tracker"):
            self.assertIn("Sr-0w/ha-bpost", manifest[key])


class HacsTest(unittest.TestCase):
    def test_required_keys(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertFalse(hacs["content_in_root"])
        self.assertEqual(hacs["filename"], "bpost.zip")
        self.assertIn("sensor", hacs["domains"])
        self.assertIn("device_tracker", hacs["domains"])


class TranslationsTest(unittest.TestCase):
    def test_json_valid(self):
        files = [INTEGRATION / "strings.json", *sorted(
            (INTEGRATION / "translations").glob("*.json"))]
        self.assertGreaterEqual(len(files), 2)
        for path in files:
            with self.subTest(path=path.name):
                json.loads(path.read_text(encoding="utf-8"))

    def test_config_step_present_everywhere(self):
        """Every locale must describe the user + reauth steps."""
        for path in sorted((INTEGRATION / "translations").glob("*.json")):
            with self.subTest(path=path.name):
                data = json.loads(path.read_text(encoding="utf-8"))
                steps = data["config"]["step"]
                self.assertIn("user", steps)
                self.assertIn("reauth_confirm", steps)


if __name__ == "__main__":
    unittest.main()
