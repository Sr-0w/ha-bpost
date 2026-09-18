# My bpost for Home Assistant

[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![release](https://img.shields.io/github/release/Sr-0w/ha-bpost.svg)](https://github.com/Sr-0w/ha-bpost/releases)
[![validate](https://github.com/Sr-0w/ha-bpost/actions/workflows/validate.yml/badge.svg)](https://github.com/Sr-0w/ha-bpost/actions/workflows/validate.yml)

Unofficial Home Assistant integration for **My bpost** (Belgium). It logs in
with your My bpost account and exposes your parcels as entities — no scraping,
no manual tokens: just your email and password.

> **Disclaimer:** community project, not affiliated with bpost. It talks to
> the same JSON API as the official Android app, so a bpost app/backend
> update can break it until a new release adapts.

## Features

- Automatic discovery of every parcel linked to your account
- One sensor per parcel (status, sender, ETA, last event, pickup point…)
  plus a `sensor.my_bpost_packages` counter
- `device_tracker` entities when bpost provides coordinates
- Full per-parcel history with timestamps (attributes)
- Events for automations: `bpost_new_package`, `bpost_status_changed`,
  `bpost_out_for_delivery`, `bpost_delivered`
- UI setup (FR / NL / EN / DE), re-authentication flow, redacted diagnostics

## Installation (HACS)

1. In HACS, open the ⋮ menu → **Custom repositories**, add
   `https://github.com/Sr-0w/ha-bpost` with category **Integration**.
2. Install **My bpost**, then restart Home Assistant.
3. Go to Settings → Devices & Services → Add Integration → **My bpost**,
   and enter your My bpost email + password.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Sr-0w&repository=ha-bpost&category=integration)

### Manual installation

Download `bpost.zip` from the
[latest release](https://github.com/Sr-0w/ha-bpost/releases), extract it so
that `custom_components/bpost/manifest.json` lands in your Home Assistant
`config` directory, then restart.

## Entities

| Entity | Description |
|---|---|
| `sensor.my_bpost_packages` | Number of active parcels (+ totals, codes, last fetch) |
| `sensor.my_bpost_<sender>` | One per parcel; state = status, attributes = sender, cities, ETA, last event, pickup point, history |
| `device_tracker.my_bpost_<sender>` | Present when coordinates are available |

Polling defaults to every 10 minutes. Automations can trigger on the
`bpost_*` events above (payloads carry the parcel code and statuses).

## About the client key

The bpost backend requires a client key (`x-api-key`) on every call. This
repository never stores it: the release asset is built by CI, which injects
the key from a maintainer secret. You only ever enter your email and
password.

If bpost rotates the key or ships an incompatible app update, the
integration will report an authentication/connection error until a new
release is published — please open an
[issue](https://github.com/Sr-0w/ha-bpost/issues) with your diagnostics
(personal data is redacted automatically).

## Development

```text
custom_components/bpost/   # integration (config flow, coordinator, platforms)
pybpost/                   # standalone async client (source of truth)
scripts/extract_key.py     # re-derive the x-api-key from the official app lib
tests/                     # packaging guards (manifest, hacs.json, no key leak)
```

`pybpost/` is vendored into the release asset by
`.github/workflows/release.yml`, which also injects the key and checks that
`manifest.json` matches the release tag. To cut a release: bump
`version` in `custom_components/bpost/manifest.json` (and
`pybpost/pyproject.toml`), push, then publish a GitHub release tagged
`vX.Y.Z` — CI attaches `bpost.zip` automatically.

## License

[MIT](LICENSE)
