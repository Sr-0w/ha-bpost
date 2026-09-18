"""Packaging guards for the ha-bpost repository (stdlib only).

Run:  python3 -m unittest discover -s tests -v

These tests protect the HACS distribution contract:
- the generic bpost client key ships embedded in source (never a placeholder);
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
    def test_embedded_api_key_well_formed(self):
        """The generic x-api-key ships in source; never a placeholder."""
        import re

        const = ROOT / "pybpost" / "pybpost" / "const.py"
        text = const.read_text(encoding="utf-8")
        self.assertNotIn("REPLACE_ME", text)
        match = re.search(r'X_API_KEY = "([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertEqual(len(match.group(1)), 40)

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
        # hacs/action rejects HA-manifest keys here (iot_class, domains…).
        self.assertTrue(
            set(hacs).isdisjoint(
                {"iot_class", "domains", "codeowners", "config_flow", "version"}
            )
        )

    def test_manifest_key_order(self):
        """Hassfest requires domain, name, then alphabetical order."""
        manifest = json.loads(
            (INTEGRATION / "manifest.json").read_text(),
            object_pairs_hook=dict,
        )
        keys = list(manifest)
        self.assertEqual(keys[:2], ["domain", "name"])
        self.assertEqual(keys[2:], sorted(keys[2:]))


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
