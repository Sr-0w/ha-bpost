# My bpost development roadmap

Goal: a reliable My bpost account integration, with useful delivery automation
and a complete live-delivery experience when the backend supplies live data.

## Verified comparison

Reference inspected: [ha-parcel-integrations/ha-bpost](https://github.com/ha-parcel-integrations/ha-bpost/tree/7e4fde618c6346e56a9a23d075a7c7f2cb43029a),
commit `7e4fde618c6346e56a9a23d075a7c7f2cb43029a` (inspection: 2026-10-05).
This is a static source comparison, not a runtime certification of that project.

| Capability | Reference integration | This repository |
| --- | --- | --- |
| Account and public barcode tracking | Both implemented | Account + independent public parcel entries (0.7.0) |
| Rotating tokens without password persistence | Implemented | Implemented; real HA account/refresh/reload check passed |
| Incoming/outgoing summaries, canonical statuses | Implemented | Implemented with raw status preserved and conservative unknown mapping |
| Calendar and device triggers | Implemented | Per-account calendar and nine device triggers, including ETA and mail announcements |
| Mail Ahead images | Implemented | Capability/count/announcements and opt-in native images; real populated backend validation remains conditional |
| Dynamic polling and retention settings | Implemented | Adaptive account/live polling and configurable inactive-entity retention |
| `getparcelchunks` live courier tracking | No implementation found in inspected source | Client, coordinator, sensors, courier tracker and card wired; eligible real delivery still needed to validate backend live payloads |
| Dedicated Lovelace card | Dashboard examples found | Bundled card, visual editor, timeline, translations, sorting and discreet mode |

Do not claim live tracking is unique across HACS or available for every parcel.
Prove backend eligibility, units, expiry, and missing-data behavior using
redacted real responses before advertising it.

## Delivery 1: durable sessions (implemented and validated)

- Consume passwords once; restore and persist access/refresh tokens.
- Serialize authentication refresh and retry a rejected request once.
- Separate temporary failures from authentication rejection in both client and HA.
- Migrate old entries without network dependencies, remove stored passwords,
  preserve entity IDs, and request one explicit sign-in.
- Reload only for changed options, not token rotation.
- Remove account identity, tracking IDs, and location data from diagnostics.
- Exercise synthetic HTTP failures and real Home Assistant entry/flow objects in CI.

Validation: client and HA tests passed, runtime startup succeeded, and authenticated
login, parcel reads, sensor setup, token rotation and reload passed against the
real account through the cloud proxy. No account credentials are stored in source.

## Delivery 2: trustworthy parcel lifecycle (implemented)

- Normalize statuses while preserving `raw_status`; unknown values stay unknown.
- Emit delivered only for confirmed delivery transitions; do not treat inactive
  parcels as delivered or reannounce all history after restart.
- Include account identity in unique IDs with a registry migration preserving
  existing entity IDs; cover the same parcel appearing in two accounts.
- Use HA's tracker entity contract and separate pickup location from courier GPS.
- User-configurable entity retention (1–365 days, default 7) and registry purge after
  successful full fetches. Inactivity age survives restart; account entities and
  active parcels remain. Backend reactivation recreates expired parcel entities.
  Recorder history follows HA's independent retention policy.

## Delivery 3: live delivery, end to end (implemented; backend validation conditional)

- Remaining: validate `getparcelchunks` on an eligible real delivery. The account
  checked had none. Progress units remain unproven, so no percentage is displayed.
- Separate account discovery cadence from optional live polling; respect
  backoff, server guidance, and a per-account request budget.
- Expose stops, ETA, courier position, and observation time. Mark stale data
  unavailable. Do not substitute zero stops or pickup coordinates for missing live data.
- Keep automation working with dashboards closed. Add a translated card view
  showing freshness, ETA, stops, and optional map.
- Test no-live-data, end-of-delivery, restart, multiple parcels, and rate limiting.

Implemented in 0.3.0: conservative typed parsing, independent live polling,
two live requests per rolling minute, server refresh guidance, shared HTTP 429
backoff, expiring GPS observations, optional live tracking, separate pickup and
courier trackers, stops/ETA/freshness on the card and a native HA map action.
The card supports account/direction filters and renamed entities.

Validation of 0.3.0: 47 client/packaging/model tests, 29 HA tests including real platform
setup with a synthetic delivery, eight Node rendering/interaction tests, and a
Chromium smoke check. The real account setup/refresh/reload check passed again.
HACS/hassfest GitHub action jobs remain to be run in GitHub; no release is published.

## Delivery 4: everyday value and distribution

- Implemented in 0.4.0: account calendars (Belgian timezone, all-day fallback,
  stable event identities) and eight device triggers with account filtering,
  including persisted changes of the account ETA. The initial ETA and missing
  date are not change notifications. No extra account polling is introduced.
- Incoming/outgoing summaries already implemented in 0.3.0.
- Pickup deadline reminders only where deadline information is actually supplied.
- Implemented in 0.5.0: Mail Ahead capability, rolling-window count, hashed
  persisted announcement baseline and opt-in image entities. Independent polling
  isolates mail failures; native image proxy access is tested with synthetic scans.
- Implemented in 0.6.0: visual card editor with account selection, filters,
  sorting, history/live toggles and discreet mode, with browser focus and mobile checks.
- Implemented in 0.6.0: parcel and letter notification blueprints using native
  Companion app device actions, account/direction filters, languages, optional
  quiet hours and per-item notification replacement tags.
- Synthetic demo data and browser tests; bounded history and Recorder impact.
- HACS/hassfest checks and upgrade tests before release. A manifest quality-scale
  label or number of test files alone does not establish quality.

Validation of 0.4.0: 47 client/packaging/model tests, 37 Home Assistant tests and
eight Node tests pass (92 total). The real HA runtime test covers calendar service
responses, device-trigger discovery, retention removal, restart without recreated
history, and backend reactivation with and without a restart. Separate tests cover
account isolation, ETA deduplication, outages, configurable retention and Belgian
summer/winter timezone offsets. A read-only live account check passed for account
setup, sensors, calendar, eight device triggers, token refresh and reload. Retention
expiry and delivery transitions use synthetic data; no real parcel was changed.
The local HA frontend/card startup smoke check also passed. Version 0.4.0 is
prepared in the workspace, not published as a GitHub release.

No competitor source code has been copied into this implementation.

Mail protocol reference additionally inspected on 2026-10-06 at competitor commit
`62edb169af201813291c94176c1b17a51fc8ee2b`: endpoint/body names and reconstructed
payload fields. Real account checks confirmed `mails/getmailsummary` flags and the
empty `mmt/retrieveImages` map. bpost reports this account not subscribed and not
eligible, so real scan delivery and image-host coverage remain unverified.

Validation of 0.5.0: 57 client/model/packaging tests, 45 HA tests and eight Node
tests pass (110 total). A full HA mail runtime exercises opt-in, image-token
access, unauthorized refusal, private attributes, announcements, restart,
temporary failure, image removal/reappearance and opt-out. Synthetic HTTP tests
verify missing account headers/cookies, URL constraints, redirects, image types,
size limits and shared rate-limit pauses. HA lifecycle tests restore bootstrap's
process-wide blocking-call wrappers between instances so both runtime scenarios
execute with blocking detection enabled.

The live account flow, parcel/calendar setup, nine device triggers, Mail Ahead
capability, token rotation and reload passed on 2026-10-06. Startup and frontend
HTTP checks also passed. Version 0.5.0 remains local; HACS/hassfest GitHub actions
and release publication have not been run.

## Delivery 5: visual configuration and notifications (0.6.0)

The card now provides HA's `getConfigElement` editor contract and emits
`config-changed` without discarding other configuration keys. It discovers account
titles with a state-based fallback, preserves unavailable selections and input
focus, and offers direction/history/live controls, four sort orders and discreet
mode. Discreet mode omits personal parcel fields and map targets from the rendered
card; it does not change entity permissions or other views.

Two Companion app blueprints cover parcel events and new letters. They filter by
the chosen account device, support FR/EN/NL/DE, optional quiet hours and a dashboard
destination. Parcel notifications optionally include tracking/ETA details; names,
addresses and scan links are never attached. Opaque per-item tags support mobile
notification replacement. Quiet-hour events are skipped, not postponed.

Validation: 57 client/model/packaging tests, 50 HA tests and 15 Node tests pass
(122 total). Blueprint tests load the actual YAML through HA validation and run
the automation engine plus native mobile device action, with a local notification
service sink. They cover account/direction/event filtering, privacy, language,
replacement tags and quiet-hour boundaries across midnight. No real phone received
test notifications. Full HA bootstrap tests run in separate processes to isolate
HA's process-wide instrumentation and shared DNS instance. Entry reloads are still
exercised within each running HA instance.

Chromium checks pass for mobile rendering, editor controls, live preview, filtering,
discreet mode and focus/caret preservation. The live account setup, token rotation,
calendar, mail capability and reload check passed on 2026-10-06. The cloud setup
script now installs pinned native-action test dependencies and stages blueprints
without overwriting existing copies. This version remains unpublished.

## Distribution hardening (0.6.0, 2026-10-06)

Corrected two HACS installation defects: release ZIP selection was not enabled,
and the asset included parent directories that HACS's extractor does not expect.
A shared deterministic builder now bundles the client and existing brand assets
without modifying the checkout. CI and release upload test the actual archive.

Validation: 59 client/packaging tests, 51 HA tests and 15 Node tests pass (125).
The full HA parcel and mail scenarios install from the ZIP. A new legacy migration
scenario exercises native reauthentication, stable entity IDs and custom names,
preserved options, password removal on disk, exact frontend serving and reload.
Nine official HACS validators and its actual ZIP extractor pass. Hassfest from
HA 2026.2.3 passes without warnings after declaring the empty YAML schema.
The live account check also passes from an ephemeral ZIP installation.

See [distribution validation](distribution-validation.md) for pinned sources,
artifact hash, reproduction and precise limits. GitHub Actions and remote release
installation remain unrun until these local changes are pushed/published. Real
courier/Mail Ahead payloads remain outstanding; public-barcode tracking was
subsequently delivered in 0.7.0.

## Delivery 6: public barcode tracking (0.7.0)

Added account-free public tracking through `track.bpost.cloud/track/items`, using
the barcode and delivery postal code. The setup menu creates an independent entry
per parcel, with validation before save, options for display/direction/retention,
and ordinary HA deletion. Shared parcel entities, calendars, pickup trackers,
card rendering and eight device triggers work across both source types. Public
entries never call account authentication, Mail Ahead or courier-round endpoints.

Protocol fields were checked against an owned parcel on 2026-10-06; only field
names/types were printed. Competitor protocol reference: commit
`62edb169af201813291c94176c1b17a51fc8ee2b`. No competitor implementation was copied.
The parser keeps unrecognized statuses unknown, accepts explicit delivery dates,
and does not guess role or ETA from ambiguous fields. Public courier enrichment,
bulk barcode import and parcel-management services remain possible follow-ups.

Validation: 69 client/model/packaging tests, 53 HA tests and 15 Node tests pass
(137 total). Coverage includes encoded query values, cookie/auth isolation,
bounded responses, HTTP failures/redirects/rate limits, flow errors/duplicates,
options, diagnostics, outage recovery, account coexistence and an actual second
HA process restoring persisted entries before isolated deletion.

The real public HA flow, status, reload and deletion passed using an owned parcel;
the live account setup/token checks also passed. Official HACS validators,
HACS ZIP extraction and HA 2026.2.3 hassfest pass locally. Remote GitHub Actions
and release publication remain pending. See the current distribution report.

## Delivery 7: daily parcel workflows (0.8.0)

All five improvements are implemented: exact-barcode duplicate filtering across
sources; grouped notifications and daily/pickup reminders; bulk manual management
and groups; a Today card view; and diagnostic health with distinct failure and
optional-capability states. See [daily workflows](daily-workflows.md) for usage,
source selection, partial imports and notification-delivery limits.

Validation: 69 client/model/packaging, 65 Home Assistant and 18 Node tests pass
(152 total). Added coverage includes source failures/ties, accumulated and late
ETA changes, persisted notification deduplication, a real timer → event → native
mobile action pipeline, private daily summaries, partial/rate-limited imports,
non-admin refusal, account deletion protection and recovery health. Chromium
exercises Today groups, duplicate controls, editor input and privacy. Backend
failure/transition scenarios are synthetic; notification actions use a local sink.

A separate live API check from the 0.8.0 ZIP passed account/public coexistence,
deduplicated summary, health entities, idempotent batch addition, reload and
isolated manual deletion, alongside the account/session/calendar checks.
HACS/hassfest, ZIP extraction and persistent HA frontend checks pass locally.
This is implemented functionality, not a claim that every feature is absent from
the competitor's current version; the reference comparison above is dated.
