# Distribution validation — 2026-10-06

## Review follow-up: 0.8.0b2

Local validation: **154 passed** (70 client/packaging, 66 HA, 18 frontend).
ZIP SHA-256: `34f0452d1bc3f22c8e25baa4ad4184652a9c9df716a3c8d74c55591bf4badb0c`. Publication/CI results are recorded in PR #1 and the release.

The Mail Ahead finding was reproduced through native HA unload/setup: a second
letter appeared while the entry was unloaded and produced zero announcements.
Loading the persisted mail baseline before the first refresh fixes this: the new
letter announces once, existing letters and subsequent reloads stay silent.
A startup mail outage also preserves the baseline, leaves parcels available,
and announces only the new letter on recovery. Payloads are synthetic.

The reported unload leak is **not reproduced on the minimum HA 2026.2.3**.
`DataUpdateCoordinator.__init__` registers `self.async_shutdown` via
`config_entry.async_on_unload`; HA awaits these callbacks after successful unload.
Native account/public reload and removal tests pass on the original code: all
three coordinator timers/listeners are stopped, stale refreshes make no calls,
a real owned aiohttp session is closed, and HA's shared session remains open.
The implementation documents that existing lifecycle rather than invoking a
second shutdown explicitly.

## Beta artifact: 0.8.0b1

Prepared 2026-10-06, with a separate beta version and matching client/tag. The
40-file archive SHA-256 is `219e5b7171b72dd368cb836c106338cb883e4a728699739acd9a2068d479e4b8`.

- 153 local tests pass: 70 client/model/packaging, 65 Home Assistant and 18 Node.
- Minimum Home Assistant is now **2026.2.3**, matching the runtime test pin.
  An isolated HA 2025.1.0 installation with its exact frontend failed at actual
  integration setup: `async_register_admin_service` did not accept
  `supports_response`. This is an application/API incompatibility, not missing
  test dependencies. That minimum was therefore no longer supportable.
- Release automation tests the ZIP before uploading it and also uploads the three
  blueprint YAML files, so beta users can install them before a PR is merged.
- GitHub CI, prerelease publication and remote HACS asset checks are tracked in
  the beta PR/release. Local test results alone do not establish those outcomes.

## Previous local artifact: 0.8.0

Local working tree, not published. Built from the shared deterministic builder,
with 40 files including `services.yaml` and the three new backend modules.
SHA-256: `aa5b6c5e03652d4d7d2dc30c643439f953979cfbc93f51733dc6afe05bb63125`.

- **152 tests passed**: 69 client/model/packaging, 65 Home Assistant and 18 Node.
  HA archive scenarios use this ZIP. No skipped tests in these suites.
- Chromium exercises real card/editor rendering, Today groups, duplicate toggle,
  group filtering, privacy and focus. Screenshots use fictional data.
- All nine applicable official HACS validators, its actual ZIP extractor, and
  HA 2026.2.3 hassfest pass locally using the pinned sources below.
- Native HA tests cover partial bulk imports, syntactic rejection before adding,
  rate-limit pauses, non-admin refusal and account-protected deletion. Grouped
  alerts cover source fallback, ETA thresholds/late estimates, persisted baseline
  reload and actual timer-to-blueprint-to-mobile-action delivery to a test sink.
- The daily blueprint is validated and its action sequence runs in HA with
  deduplicated private counts and pickup-only filtering. Its wall-clock scheduling
  relies on the native HA time trigger; a real overnight schedule was not observed.
- The **live API check** in an ephemeral HA installation passes account login,
  token rotation, sensors/calendar/nine triggers/mail capability/reload, and public
  tracking of an owned parcel. Cross-source summary deduplication, both health
  sensors, idempotent batch addition and manual removal via actions also pass.
  No barcode, postal code, tokens or credentials were printed.
- The reusable setup ran successfully, including module/menu/service and exact
  frontend/card HTTP checks. Persistent development HA was restarted; every staged
  archive file and the served card match this ZIP.

HA/Python/frontend versions remain 2026.2.3 / 3.13.15 / 20260128.6. No real phone
received a test notification. The final HA test run fixes a unit-test teardown
race: the synthetic auth failure now verifies reauthentication scheduling without
starting an unrelated HTTP stack in that unit fixture; native reauth still runs
in the separate full migration test.

New grouped alerts require replacing existing parcel blueprint copies and
reloading automations. A pending 30-second notification window is not durable;
raw custom automations retain their earlier behavior. Details and examples are
in [daily workflows](daily-workflows.md). GitHub Actions, release upload and
remote HACS installation remain unrun. Eligible real courier/Mail Ahead data and
other HA versions remain the limits documented below.

## Previous artifact: 0.7.0

Local working tree, not published. The ZIP has 36 files and includes both public
tracking modules. SHA-256:
`064742009ab9f970e832255cf9aaa3bb9c90e190dc573af00ba6a278258a38ec`

The Python/HA/frontend versions and official validator sources below are unchanged.
Build with `python scripts/build_release.py --tag v0.7.0 --output bpost.zip`.

- 69 client/model/packaging tests, 53 HA tests and 15 Node tests: **137 passed**.
- Nine official HACS validators, the real HACS ZIP extractor and all integration
  hassfest checks pass locally.
- The public runtime scenario starts a second HA process against the same
  configuration directory. It verifies stable entry/entity identities, saved
  options, no duplicate announcements, and deletion without affecting an account
  tracking the same parcel. Backend responses in this test are synthetic.
- A separate **real API** check uses an owned parcel obtained from the secure
  account session, adds it through the public HA flow, checks its status, reloads
  and removes it. All passed; no barcode, postal code or credentials were printed.
- The account login, token rotation, calendar, device triggers, mail capability
  and reload check still passes from this ZIP. Setup also exercises the new
  account/public menu and exact frontend/card HTTP content.

Public tracking sends no account credentials, cookies or generic client key.
Manual entries retain their barcode/postal code in HA configuration; diagnostics
redact them. Mail Ahead and courier GPS/stops remain account-only. Public status
and protocol variants are not exhaustively verified; unknown codes remain unknown.
GitHub Actions and remote release installation remain unrun. The previously
documented minimum-HA-version and real courier/Mail Ahead limits still apply.

## Previous artifact: 0.6.0

Version **0.6.0**, local working tree; not a published release. The cloud runtime
uses Home Assistant **2026.2.3**, Python **3.13.15** and frontend **20260128.6**.

## Corrected installation contract

`hacs.json` previously named `bpost.zip` without enabling `zip_release`. HACS could
therefore install repository sources without the release-only bundled client.
The old ZIP also contained `custom_components/my_bpost/`, whereas HACS's release
extractor writes directly into that directory. The new builder produces the flat
integration archive and `zip_release: true` selects it.

The archive contains 34 files: integration/client Python modules, translations,
frontend, existing brand images and license. It excludes bytecode, test helpers,
configuration, blueprints and development files. Blueprints remain separate.

Validated ZIP SHA-256:
`75556e12a45889657dc201a54584935aa5be8eb985da4252da8949dcbd7c590c`

## Results

| Check | Result |
| --- | --- |
| Client/model/packaging tests | 59 passed |
| Home Assistant tests | 51 passed |
| Frontend Node tests | 15 passed |
| Hassfest, HA 2026.2.3 | All integration validators passed; no warnings |
| Official HACS validators with local files and live GitHub metadata | All 9 applicable checks passed |
| Official HACS ZIP extraction | Passed; every extracted file equals the archive |
| Fresh HA installations from the ZIP | Parcel/courier/calendar and mail/image runtime scenarios passed |
| v1 account migration from legacy 0.2.0 data/registry shape | Passed; local migration, reauthentication, stable IDs/names/options, no stored password |
| v2 token-account reload | Passed; no additional password login or duplicate announcements |
| Live account in an ephemeral HA config extracted from the ZIP | Login, parcels, calendar, 9 triggers, mail capability, token rotation and reload passed |
| Reusable cloud setup | Completed, including the 125 tests and frontend/card HTTP smoke check |
| Persistent development HA | Restarted; frontend HTTP 200; staged files match the ZIP |

Migration coverage constructs the actual v1 entry and unscoped sensor/tracker IDs
used by 0.2.0. It runs HA's migration, reauthentication and platform lifecycle using
the new archive. It does not boot the old integration first. Backend responses in
automated runtime tests are synthetic; the separate live check uses secure
environment bindings and emits no personal data. No real notifications are sent.

## Official validator sources and reproduction

- HACS integration source: `adb7d83e33d24325535fb43b8226572405143757`.
- Hassfest from HA 2026.2.3: `9c640fe0fa008d6e80aa4cc88c9c1734605fb3e0`.

After installing the repository's development dependencies in a Python 3.13
environment, build and test the artifact from the repository root:

```sh
python scripts/build_release.py --tag v0.6.0 --output bpost.zip
BPOST_RELEASE_ZIP="$PWD/bpost.zip" python -m unittest discover -s tests/ha -v
```

For the official validators, use separate dependency checkouts; do not vendor HACS
or Home Assistant sources into this repository. The validation environment also
needs `ruff==0.14.13` and `aiogithubapi==26.0.0`. Install
`hacs_frontend==20250128065759` into the HACS checkout's `custom_components/hacs/`
directory, as its action does. The HACS helper runs only the applicable validators
and the ZIP extractor; it does not start HACS or pretend to be a GitHub Action.

```sh
git clone https://github.com/hacs/integration.git /tmp/my-bpost-hacs
git -C /tmp/my-bpost-hacs checkout --detach adb7d83e33d24325535fb43b8226572405143757
python -m pip install ruff==0.14.13 aiogithubapi==26.0.0
python -m pip install --target /tmp/my-bpost-hacs/custom_components/hacs hacs_frontend==20250128065759
python scripts/validate_hacs_local.py --hacs-source /tmp/my-bpost-hacs --archive bpost.zip

git clone --depth 1 --branch 2026.2.3 --filter=blob:none --sparse https://github.com/home-assistant/core.git /tmp/my-bpost-hassfest
git -C /tmp/my-bpost-hassfest sparse-checkout set script/hassfest script/translations script/util
# Run in the hassfest checkout, with the same Python environment active:
cd /tmp/my-bpost-hassfest
python -m script.hassfest --integration-path /absolute/path/to/ha-bpost/custom_components/my_bpost
```

The cloud helper uses the configured HTTP proxy and normal TLS verification for
GitHub metadata. No GitHub or bpost credentials are embedded in these commands.

## Remaining limits

- GitHub Actions have not run for these unpushed changes. The existing CI uses
  moving HACS/hassfest action references; local results above identify exact
  sources and do not establish a future run's result.
- The 0.6.0 release asset has not been uploaded. Remote release discovery and
  downloading that published asset through HACS remain to be checked after release.
- HA runtime coverage is for 2026.2.3; the declared minimum 2025.1.0 and other HA
  versions have not been runtime-tested in this lot.
- The live account has no eligible courier round or populated Mail Ahead inbox.
  Actual courier payloads, populated letter responses and scan-host coverage
  remain unverified, despite synthetic runtime/HTTP coverage.
- Manual public-barcode tracking was subsequently implemented and validated in
  0.7.0; bulk management and daily workflows followed in 0.8.0.
