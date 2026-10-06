# Installation and upgrades

[Documentation](README.md) · [Project overview](../README.md)

Requires **Home Assistant 2026.2.3+**. These guides describe the 0.8 beta.
An account is optional when tracking a parcel by barcode and postal code.

## HACS

1. In HACS, open the ⋮ menu → **Custom repositories**, add
   `https://github.com/Sr-0w/ha-bpost` with category **Integration**.
2. Enable beta versions for this repository, install **v0.8.0b2**, and restart
   Home Assistant.
3. Go to Settings → Devices & Services → Add Integration → **My bpost**,
   choose **My bpost account**, and enter your email + password.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sr-0w&repository=ha-bpost&category=integration)

For account-free setup, see [manual tracking](tracking.md#track-a-parcel-without-an-account).
For multiple barcodes, see [bulk import](daily-workflows.md#import-and-manage-manual-parcels).

## Manual installation

Download `bpost.zip` from the
[releases](https://github.com/Sr-0w/ha-bpost/releases). For the 0.8 beta, extract
its contents **into `config/custom_components/my_bpost/`**, then restart.
The archive root contains `manifest.json`, `pybpost/` and `frontend/`; do not
extract it directly into `config/`. Earlier archives included the
`custom_components/my_bpost/` parent directories.

Use the release asset for installation: the source checkout alone does not include
the bundled Python client. [Notification blueprints](notifications.md) are installed separately.

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
