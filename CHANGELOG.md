# Release notes

## 0.8.0b1 — beta

Minimum Home Assistant: **2026.2.3**. HA 2025.1 fails to register admin services
with responses; HACS now prevents installing this release on that version.
The beta is opt-in and includes all unreleased improvements below since 0.2.0.

- Deduplicate exact barcodes across account/manual sources in the card, summaries
  and grouped alerts, with available/fresh source selection and stable tie breaks.
- Group parcel updates over 30 seconds, persist announcement baselines and apply
  a configurable material-ETA threshold. Add private daily/pickup reminders.
- Import up to 20 manual parcels, assign groups and use admin HA actions for
  addition/removal. Return partial results and protect account entries.
- Add a Today card view with problems, pickups and due deliveries in HA local time.
- Add readable diagnostic health with explicit auth, rate-limit and outage states,
  last-success/retry timestamps and optional-feature capabilities.

Replace existing parcel blueprint copies and reload automations to adopt grouped
alerts; use one all-sources automation for household deduplication. Raw custom
automations retain their existing behavior. Notification windows pending at
shutdown are not durable. Details: [daily workflows](docs/daily-workflows.md).

## 0.7.0 — unreleased

- Added public parcel tracking by barcode and delivery postal code, without an
  account. Add one entry per parcel through the integration setup menu.
- Manual entries support names, direction, retention, calendars, pickup locations,
  eight parcel triggers and the existing card/notification blueprint.
- Public transport sends no account credentials/cookies, bounds response sizes,
  refuses redirects and respects rate limits. Inputs are redacted in diagnostics.
- Outages preserve configured parcels. Tests cover options, duplicates, account
  coexistence, real HA process restart and isolated entry deletion.
- Verified with an owned parcel through the real public API and HA config flow,
  including reload and deletion. Live account/token tests still pass.

Manual entries do not provide Mail Ahead or courier GPS/stops. Adding a parcel
already discovered by an account creates a separate source. Existing accounts
keep their configuration; setup now starts with an account/public-tracking menu.

## 0.6.0 — unreleased

- Renewable account sessions; passwords are consumed at login and removed from
  legacy entries. Refresh failures request reauthentication; outages retain data.
- Stable parcel statuses, incoming/outgoing counters, account-scoped identities,
  adaptive polling and configurable retention of inactive parcel entities.
- Separate courier and pickup trackers, expiring live observations, delivery
  calendars, nine native device triggers and persisted announcement baselines.
- Mail Ahead capability/count sensors, letter announcements and optional scans
  through Home Assistant's image proxy. Scans are disabled by default.
- Visual card editor, account/direction filters, sorting and discreet mode.
- FR/NL/EN/DE Companion notification blueprints with account filters and optional
  quiet hours. Install and configure these separately; quiet-hour events are skipped.
- Correct HACS release-asset selection and ZIP layout, reproducible builds and
  archive-based HA installation/migration tests before upload.

### Migration from 0.2.0

Restart after upgrading. Existing accounts require one sign-in through Home
Assistant's reauthentication prompt. Migration removes the stored password while
preserving account/entity IDs, names and options. Back up before upgrading; a
rollback requires restoring both the previous integration and its matching backup.

For manual installation, extract the new ZIP **into**
`config/custom_components/my_bpost/`; its root now contains `manifest.json`.

### Validation limits

Account login, token rotation, parcel setup and reload have been checked against
the live API. The test account has no eligible courier round or populated Mail
Ahead inbox; live courier payloads and real envelope downloads remain unverified.
Those paths have synthetic API and Home Assistant runtime coverage. No test sends
a real mobile notification. This version has not been published.
