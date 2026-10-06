# My bpost for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Release](https://img.shields.io/github/v/release/Sr-0w/ha-bpost?include_prereleases)](https://github.com/Sr-0w/ha-bpost/releases)
[![Validate](https://github.com/Sr-0w/ha-bpost/actions/workflows/validate.yml/badge.svg)](https://github.com/Sr-0w/ha-bpost/actions/workflows/validate.yml)

Follow your bpost parcels in Home Assistant: see what's arriving today, what needs
collecting, and when a delivery changes. Connect your My bpost account or track
individual parcels with a barcode and delivery postal code.

Community project, not affiliated with bpost. Available in English, French, Dutch
and German.

> **Current version: [0.8.0b2 beta](https://github.com/Sr-0w/ha-bpost/releases/tag/v0.8.0b2).**
> Requires Home Assistant **2026.2.3+**. Enable beta versions in HACS to install it.

## What you get

- **Parcel dashboard** with a Today view, tracking history and a visual editor.
- **Account or manual tracking**, including bulk import, groups and duplicate filtering.
- **Delivery notifications**, daily summaries and pickup reminders through the Companion app.
- **Home Assistant entities**, delivery calendars and device triggers for your automations.
- **Mail Ahead** letter announcements and optional envelope images for eligible accounts.
- **Courier ETA, remaining stops and map** when bpost supplies live delivery data.

Mail Ahead and courier tracking depend on account eligibility and backend data.
See the [documentation](docs/README.md) for availability and limitations.

![Parcel card with fictional demonstration data](images/card-default.png)

## Install with HACS

1. Open **HACS → Custom repositories** and add
   `https://github.com/Sr-0w/ha-bpost` as an **Integration**.
2. Enable beta versions for this repository, install **v0.8.0b2**, and restart
   Home Assistant.
3. Go to **Settings → Devices & services → Add integration → My bpost**.
4. Choose your **My bpost account**, **a parcel without an account**, or **bulk import**.

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sr-0w&repository=ha-bpost&category=integration)

For manual installation or an upgrade from an older version, follow the
[installation and migration guide](docs/installation.md). Install the release's
`bpost.zip` asset; GitHub's source ZIP does not include the bundled client.

## Add your dashboard

In the dashboard editor, add the **Bpost Parcels** card. Its visual editor offers
Today/all-parcels views, account and group filters, history and discreet mode.
The card is registered automatically. A minimal YAML configuration is:

```yaml
type: custom:my-bpost-parcels-card
view: today
```

To receive phone alerts, install and configure a
[notification blueprint](docs/notifications.md). Notifications are opt-in.

## Documentation

| Guide | Contents |
| --- | --- |
| [Installation and upgrades](docs/installation.md) | HACS, manual installation and migration |
| [Dashboard](docs/dashboard.md) | Card options, filters and discreet mode |
| [Notifications](docs/notifications.md) | Blueprints and automation triggers |
| [All guides](docs/README.md) | Tracking, Mail Ahead, bulk actions and development |
| [Changelog](CHANGELOG.md) | Changes by published version |

## Help and contributions

Report problems in [GitHub issues](https://github.com/Sr-0w/ha-bpost/issues).
Include your HA/integration versions and redacted diagnostics; never share
credentials, tracking numbers or letter scans.

For local setup, tests and release packaging, see the
[development guide](docs/development.md).

[MIT license](LICENSE).
