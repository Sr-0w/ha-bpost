# Documentation

[Project overview](../README.md) · [Changelog](../CHANGELOG.md)

These guides describe the **0.8 beta**, requiring Home Assistant **2026.2.3+**.
Start with installation, then choose the guides relevant to your setup.

## Set up and use My bpost

| Guide | What it covers |
| --- | --- |
| [Installation and upgrades](installation.md) | HACS, the release ZIP, account setup and migrations |
| [Parcels and tracking](tracking.md) | Manual parcels, entities, statuses, retention, calendars and courier data |
| [Dashboard card](dashboard.md) | Visual editor, card configuration, sorting and discreet mode |
| [Notifications and automations](notifications.md) | Companion blueprints, quiet hours and raw device triggers |
| [Daily workflows](daily-workflows.md) | Duplicate selection, bulk actions, groups, Today summaries and health |
| [Mail Ahead](mail-ahead.md) | Eligibility, letter counts, private scans and announcement events |

## Availability and privacy

Public barcode tracking does not provide Mail Ahead or courier GPS/stops. Those
features require account data from bpost; an account may have neither. Real courier
payloads and populated Mail Ahead scans still have limited validation; see the
[validation report](distribution-validation.md#current-limits) for details.

Discreet mode hides details on the parcel card, not in other HA views. Account
tokens, tracking inputs and letter images remain private data. The relevant guides
explain storage, access and notification behavior.

## Development and project records

- [Development](development.md): dependencies, tests, archive builds and the client key.
- [Python client](../pybpost/README.md): standalone API examples.
- [Changelog](../CHANGELOG.md): published versions and upgrade highlights.
- [Distribution validation](distribution-validation.md): dated test evidence,
  archive hashes and validation limits. Historical entries describe their own version.
- [Engineering roadmap](roadmap.md): dated competitor comparison and implementation
  history; this is a project record, not an installation guide.
