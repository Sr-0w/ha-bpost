"""Packaging guards for the ha-bpost repository (stdlib only).

Run:  python3 -m unittest discover -s tests -v

These tests protect the HACS distribution contract:
- the generic bpost client key ships embedded in source (never a placeholder);
- the client is committed inside the integration HACS installs;
- manifest.json / hacs.json keep the metadata HACS and Home Assistant require;
- shipped JSON files stay valid.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.check_release import check_release

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION = ROOT / "custom_components" / "my_bpost"


class SourceHygieneTest(unittest.TestCase):
    def test_embedded_api_key_well_formed(self):
        """The generic x-api-key ships in source; never a placeholder."""
        import re

        const = INTEGRATION / "pybpost" / "const.py"
        text = const.read_text(encoding="utf-8")
        self.assertNotIn("REPLACE_ME", text)
        match = re.search(r'X_API_KEY = "([^"]+)"', text)
        self.assertIsNotNone(match)
        self.assertEqual(len(match.group(1)), 40)

    def test_client_is_committed_inside_the_integration(self):
        """HACS installs this directory, so the client cannot live only in a zip."""
        client = INTEGRATION / "pybpost"
        self.assertTrue((client / "client.py").is_file())
        self.assertFalse((client / "client.py").is_symlink())
        link = ROOT / "pybpost" / "pybpost"
        self.assertTrue(link.is_symlink())
        self.assertEqual(link.resolve(), client.resolve())

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
        self.assertEqual(manifest["domain"], "my_bpost")
        self.assertTrue(manifest["config_flow"])
        self.assertIn("frontend", manifest.get("dependencies", []))

    def test_version_format(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:b[1-9]\d*)?$")

    def test_repo_urls_point_at_ha_bpost(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        for key in ("documentation", "issue_tracker"):
            self.assertIn("Sr-0w/ha-bpost", manifest[key])


class HacsTest(unittest.TestCase):
    def test_required_keys(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertFalse(hacs["content_in_root"])
        self.assertNotIn("filename", hacs)
        self.assertNotIn("zip_release", hacs)
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

    def test_declared_minimum_is_the_tested_home_assistant_version(self):
        minimum = json.loads((ROOT / "hacs.json").read_text())["homeassistant"]
        requirements = (ROOT / "requirements-dev.txt").read_text().splitlines()
        self.assertIn(f"homeassistant=={minimum}", requirements)


class ReleaseSourceTest(unittest.TestCase):
    def test_tagged_integration_is_self_contained(self):
        version = check_release()
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        self.assertEqual(version, manifest["version"])
        for required in ("manifest.json", "config_flow.py", "image.py", "calendar.py",
                         "pybpost/client.py", "pybpost/mail.py", "pybpost/status.py",
                         "frontend/my-bpost-parcels-card.js", "translations/fr.json",
                         "brand/icon.png", "services.yaml"):
            path = INTEGRATION / required
            self.assertTrue(path.is_file(), required)
            self.assertFalse(path.is_symlink(), required)

    def test_tag_mismatch_is_rejected(self):
        with self.assertRaises(ValueError):
            check_release(tag="v999.0.0")


class CardTest(unittest.TestCase):
    CARD = INTEGRATION / "frontend" / "my-bpost-parcels-card.js"

    def test_card_shipped(self):
        text = self.CARD.read_text(encoding="utf-8")
        self.assertIn("my-bpost-parcels-card", text)
        self.assertIn("customCards", text)
        self.assertIn("getStubConfig", text)

    def test_card_theme_safe(self):
        """No hardcoded colors or fonts: everything via HA CSS variables."""
        import re

        text = self.CARD.read_text(encoding="utf-8")
        no_fallbacks = text
        for _ in range(3):  # nested var() fallbacks
            no_fallbacks = re.sub(r"var\([^()]*\)", "var()", no_fallbacks)
        self.assertNotRegex(no_fallbacks, r"#[0-9a-fA-F]{3,8}\b")
        self.assertNotIn("font-family", no_fallbacks)


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
