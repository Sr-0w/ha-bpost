# Development

[Documentation](README.md) · [Project overview](../README.md)

## Session storage

New configurations store access and refresh tokens, never the account password.
The password is used only for the initial login or explicit reauthentication.
Rotated tokens are saved back to the Home Assistant config entry without
reloading the integration. Tokens are credentials: protect Home Assistant's
configuration directory and backups.

Existing version-1 config entries migrate locally to version 2, removing their
stored password while keeping their entry and entity IDs. They require a
one-time sign-in through Home Assistant's reauthentication flow. Temporary API
outages do not require another sign-in; a rejected refresh token does.

## Tests

Use Python 3.13. From the repository root:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e ./pybpost --config-settings editable_mode=compat
.venv/bin/python -m unittest $(find tests -maxdepth 1 -name 'test_*.py' | sort) -v
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests/ha -v
node --test tests/frontend/*.test.cjs
```

The client tests run against a local HTTP server with synthetic credentials.
The full Home Assistant runtime tests copy `custom_components/my_bpost` into a
temporary configuration directory, which is the tree HACS installs from a tag.
They do not contact bpost. They cover
config flows, migration, token rotation, reauthentication, error handling, and
diagnostic redaction, status transitions, account-scoped identities, polling limits,
retention across restart and reactivation, account-filtered device triggers,
calendar windows/timezones, and a real HA runtime with synthetic courier data.
The runtime check exercises calendar services, device-trigger discovery, entity
removal and re-creation. The Node tests check card
rendering and interactions with a minimal DOM harness, not a real browser.
Live account validation is a separate check.

## Release checks

```sh
python3 scripts/check_release.py --tag v0.8.2
.venv/bin/python -m unittest discover -s tests/ha -v
```

`scripts/check_release.py` checks that the manifest, client package and
`pyproject.toml` versions match, that the tag matches when one is given, and
that the client files are real files inside `custom_components/my_bpost/pybpost`.
HACS installs that directory from the tag. There is no separate integration zip.
The release workflow repeats the tests on the tagged commit before uploading the
blueprint YAML files.

[Distribution validation](distribution-validation.md) records the official
HACS/hassfest versions, results, reproduction commands and remaining limits.

Mail tests cover capability states, strict response parsing, private image transport,
bounded downloads, request headers, persistent announcement deduplication, failure
isolation and image cache invalidation. The full HA mail runtime test checks native
image-token access, refusal without authorization, reloads, removal, reappearance
and opt-out. No real letters or credentials are used in those tests.

An optional real Chromium check exercises the card with synthetic data and
minimal Home Assistant host elements (Playwright and system Chromium required):

```sh
CHROMIUM_EXECUTABLE=/usr/bin/chromium python3 tests/frontend/browser_smoke.py
```

Set `BPOST_ARTIFACT_DIR` to choose where its demo screenshot is saved. This check
does not authenticate or include real parcel data.

```text
custom_components/my_bpost/          # integration HACS installs from a tag
custom_components/my_bpost/pybpost/  # client source of truth
pybpost/                             # installable package; pybpost/pybpost links to the client
scripts/extract_key.py               # re-derive the x-api-key from the official app lib
tests/                               # packaging and client HTTP tests
tests/ha/                            # Home Assistant session and migration tests
```

The client is committed inside the integration so a HACS install matches the
tag. `pybpost/pybpost` is a symbolic link to that package, which lets
`pip install -e ./pybpost` import it without putting the integration directory
on `sys.path` (that would shadow Python's standard-library `calendar` module).
To cut a release, update `custom_components/my_bpost/manifest.json`,
`pybpost/pyproject.toml` and `custom_components/my_bpost/pybpost/__init__.py`
to the same version. Push and wait for validation, then publish a matching
`vX.Y.Z` tag (or `vX.Y.ZbN` prerelease). The release workflow checks the tag,
retests that source and uploads the three blueprint YAML files.

If bpost rotated the key, re-extract it first
with `scripts/extract_key.py` against the current app release.

## About the client key

The account API requires a client key (`x-api-key`). Public barcode tracking
does not send it. This is bpost's **generic application key**, shipped in the
official app and embedded in this integration. Users only enter their email and
password; no individual API key is required.

If bpost rotates the key or ships an incompatible app update, the
integration will report an authentication/connection error until a new
release is published — please open an
[issue](https://github.com/Sr-0w/ha-bpost/issues) with your diagnostics
(personal data is redacted automatically).

See also the dated [validation report](distribution-validation.md) and
[engineering roadmap](roadmap.md).
