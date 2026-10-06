# Changelog

Published changes, newest first. Installation and migration steps live in the
[upgrade guide](docs/installation.md#upgrading); detailed behavior is in the
[documentation](docs/README.md).

## [0.8.0b2](https://github.com/Sr-0w/ha-bpost/releases/tag/v0.8.0b2) — 2026-10-06

### Fixed

- Load the saved Mail Ahead announcement history before the first poll, so letters
  arriving while the integration is stopped are announced once after restart.
- Preserve that history through startup mail outages while keeping parcel tracking
  available.

### Validation

- Add native reload/removal tests for coordinator timers, listeners and HTTP
  sessions. HA 2026.2.3 already shuts the coordinators down through its entry
  lifecycle; no redundant shutdown call was added.

## [0.8.0b1](https://github.com/Sr-0w/ha-bpost/releases/tag/v0.8.0b1) — 2026-10-06

First 0.8 beta, incorporating the development milestones since 0.2.0.
Requires **Home Assistant 2026.2.3+**.

### Added

- Public parcel tracking by barcode/postal code, bulk imports of up to 20 parcels,
  groups and admin actions for adding/removing manual entries.
- Cross-source duplicate filtering, a Today dashboard view, visual card editor,
  sorting and discreet mode.
- Grouped parcel alerts, configurable material ETA thresholds, private daily
  summaries, pickup reminders and Companion app blueprints in four languages.
- Delivery calendars, parcel/letter device triggers, incoming/outgoing counters,
  canonical statuses and configurable inactive-parcel retention.
- Mail Ahead capability/count sensors and opt-in native letter images.
- Optional courier tracking with expiring positions, remaining stops and ETA,
  separate from pickup locations.
- Readable tracking health, rate-limit handling and adaptive polling.

### Changed

- Persist rotating session tokens instead of account passwords. Legacy accounts
  migrate while preserving entity identities and options, then require one sign-in.
- Correct HACS release selection and ZIP layout; bundle the client in a reproducible
  archive and test installation/migration before uploading it.
- Raise the HA minimum after confirming that 2025.1 cannot register the new
  response-capable admin actions.

### Upgrade notes

- Use the release's `bpost.zip`, extracted into `config/custom_components/my_bpost/`.
- Update existing parcel blueprint copies and reload automations for grouped alerts.
  Raw custom automations retain their prior event behavior.
- See [notification limits](docs/daily-workflows.md#grouped-parcel-alerts) and
  [migration instructions](docs/installation.md#upgrading).

Development versions 0.3–0.7 were not published separately; their changes are
included in 0.8.0b1. For older published versions, see
[GitHub releases](https://github.com/Sr-0w/ha-bpost/releases).
