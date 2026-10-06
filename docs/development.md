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
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests/ha -v
node --test tests/frontend/*.test.cjs
```

The client tests run against a local HTTP server with synthetic credentials.
The full Home Assistant runtime tests build and extract the actual release ZIP
in a temporary configuration directory;
they do not vendor files into the source checkout or contact bpost. They cover
config flows, migration, token rotation, reauthentication, error handling, and
diagnostic redaction, status transitions, account-scoped identities, polling limits,
retention across restart and reactivation, account-filtered device triggers,
calendar windows/timezones, and a real HA runtime with synthetic courier data.
The runtime check exercises calendar services, device-trigger discovery, entity
removal and re-creation. The Node tests check card
rendering and interactions with a minimal DOM harness, not a real browser.
Live account validation is a separate check.

## Release archive and distribution checks

```sh
python3 scripts/build_release.py --tag v0.8.0b2 --output bpost.zip
BPOST_RELEASE_ZIP="$PWD/bpost.zip" .venv/bin/python -m unittest discover -s tests/ha -v
```

The builder checks all three version declarations and the release tag, bundles
the client and existing brand assets, and excludes caches and development files.
Identical inputs produce identical archives. HACS extracts this ZIP directly into
the integration directory (`zip_release: true`). CI tests its built artifact, and
the release workflow repeats the HA tests before uploading it.

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
custom_components/my_bpost/   # integration (config flow, coordinator, platforms)
pybpost/                   # standalone async client (source of truth)
scripts/extract_key.py     # re-derive the x-api-key from the official app lib
tests/                     # packaging and client HTTP tests
tests/ha/                  # Home Assistant session and migration tests
```

`pybpost/` is vendored into the release asset by
`.github/workflows/release.yml`, which also checks that `manifest.json`
matches the release tag. To cut a release, update `custom_components/my_bpost/manifest.json`,
`pybpost/pyproject.toml` and `pybpost/pybpost/__init__.py` to the same version.
Push and wait for validation, then publish a matching `vX.Y.Z` tag (or `vX.Y.ZbN`
prerelease). CI retests the ZIP and attaches it with the three blueprint YAML files.
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
