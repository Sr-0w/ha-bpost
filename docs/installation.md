# Installation and upgrades

[Documentation](README.md) · [Project overview](../README.md)

Requires **Home Assistant 2026.2.3+**. These guides describe version 0.8.2.
An account is optional when tracking a parcel by barcode and postal code.

## HACS

1. In HACS, open the ⋮ menu → **Custom repositories**, add
   `https://github.com/Sr-0w/ha-bpost` with category **Integration**.
2. Install **My bpost** and restart Home Assistant.
3. Go to Settings → Devices & Services → Add Integration → **My bpost**,
   choose **My bpost account**, and enter your email + password.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sr-0w&repository=ha-bpost&category=integration)

For account-free setup, see [manual tracking](tracking.md#track-a-parcel-without-an-account).
For multiple barcodes, see [bulk import](daily-workflows.md#import-and-manage-manual-parcels).

## Manual installation

Download the source archive for a release from
[releases](https://github.com/Sr-0w/ha-bpost/releases). Copy
`custom_components/my_bpost` into `config/custom_components/`, then restart.
That folder already contains the Python client, the Lovelace card and the
translations. Releases before 0.8.1 instead published a flat `bpost.zip` that
was extracted directly into `config/custom_components/my_bpost/`.

[Notification blueprints](notifications.md) are separate release assets and are
installed separately.

## Upgrading

Keep a Home Assistant backup before upgrading. Install the new release and restart
Home Assistant. Accounts created with 0.2.0 require a one-time sign-in from the
integration's reauthentication prompt; their saved password is removed during
migration. Existing account/entity IDs, custom names and options are preserved.
Accounts already using session tokens can reload without entering a password.

To roll back a migrated account, restore the matching backup and integration
version together. Installing old files alone does not reverse the config-entry
migration. See [changelog](../CHANGELOG.md) for this release's scope.

## Migrating from 0.1.x (domain rename)

Version 0.2.0 renames the integration domain from `bpost` to `my_bpost`
so it coexists with other bpost integrations. To migrate: remove the old
**bpost** config entry, update to 0.2.0, restart, then add **My bpost**
again with your email + password. Entity IDs (`sensor.my_bpost_*`) are
usually preserved, but a few parcel IDs may be regenerated from bpost's
current name data — update anything referencing exact parcel entity IDs.
Automations must switch to the `my_bpost_*` events and dashboards to
`custom:my-bpost-parcels-card`.

## Existing automations

Parcel statuses use the [canonical states](tracking.md#parcel-statuses). Update
automations that compare old API status strings or the former `previous` tuple;
status-change events now provide `old_status` and `new_status`. See the
[event reference](notifications.md#device-triggers) for payloads.

## Account credentials

Account passwords are used for login or explicit reauthentication only. HA stores
renewable access/refresh tokens, which remain credentials: protect its config and
backups. A rejected refresh token requires signing in again; a temporary service
outage does not. [Session implementation](development.md#session-storage).
