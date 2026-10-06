# Daily workflows

[Documentation](README.md) · [Project overview](../README.md)

For blueprint installation, see [notifications](notifications.md). For visual
card configuration, see the [dashboard guide](dashboard.md).

## Matching parcels across sources

Account and manually tracked parcels keep independent config entries and entity
IDs. The card, `my_bpost.get_summary` and grouped notifications match **exact
tracking numbers**. They choose an available, recognized observation first, then
the most recent successful fetch, then the account source on a timestamp tie.
Entity ID breaks any remaining tie. Fields are never combined across sources.
The newest public observation may therefore have fewer details than an account.

Card/summary account and group filters run before selection. Card direction
filters also run first. `deduplicate: false` shows separate observations for
troubleshooting. Existing package counters, calendars and raw device triggers
remain per entry. A group is a local label, not an access-control boundary.

## Import and manage manual parcels

In **Settings → Devices & services → Add integration → My bpost**, choose the
bulk import option. Paste one barcode per nonempty line (1–20), supply the shared
delivery postal code, optional group and language. Entries are validated and added
sequentially. The result shows how many were added, already present, and which
nonempty input rows failed. Successful rows remain configured after a later
failure. HTTP 429 pauses the remaining batch; retry those rows later.

For different postal codes or labels, use the admin-only action in a script:

```yaml
- action: my_bpost.track_parcels
  data:
    parcels:
      - barcode: "REPLACE_WITH_BARCODE"
        postal_code: "1000"
        label: "Books"
        group: "Home"
        direction: incoming
        app_lang: fr
  response_variable: imported
```

Allowed directions are `incoming`, `outgoing`, `unknown` (default); languages
are `fr` (default), `nl`, `en`, `de`. Labels are limited to 80 characters and
groups to 40. All input syntax is checked before the first addition. Each result
has `row`, `status`, and an `entry_id` when added or already configured. Existing
manual barcodes are skipped without changing their options. Common failure
statuses are `tracking_not_found`, `cannot_connect` and `rate_limited`.
Input syntax failures raise an action error without adding anything.

To remove entries using the returned IDs:

```yaml
- action: my_bpost.untrack_parcels
  data:
    entry_ids:
      - "REPLACE_WITH_MANUAL_ENTRY_ID"
  response_variable: removed
```

Only manual My bpost entries can be removed; a batch containing an account or a
different integration is rejected before any deletion. Results are `removed`,
`not_found` or `failed`. Removal affects local HA tracking only. These actions
require an administrator for user-initiated calls; HA's own automations can run
them. A manual entry can also be deleted normally in Devices & services.

Entry options let you change a group; account groups apply to every parcel in
that account. New manual entries can also choose a group and direction directly.

## Today view and private summaries

```yaml
type: custom:my-bpost-parcels-card
view: today
group: Home
deduplicate: true
privacy_mode: true
```

The visual editor exposes these same controls. Today uses Home Assistant's time
zone and refreshes at least once per minute while attached. It shows disjoint
groups: problems, ready to collect, then deliveries in progress or with an ETA
on today's date. Inactive and unavailable parcels are excluded. Health warnings
remain visible, without account names in discreet mode.

`my_bpost.get_summary` returns counts only: `today`, `pickup`, `problem`, `active`,
`unavailable`, `duplicates`, `parcels`, and an `as_of` UTC timestamp. Supply an
optional `entry_id` or exact `group`; an empty group means all. Use
`response_variable` in scripts, since this action requires a response. Unknown
statuses count as unavailable. The daily blueprint uses this same summary.

The daily blueprint runs at the chosen HA local time. Its pickup-only option
requires at least one currently ready-to-collect parcel. This is a status-based
reminder: no collection deadline is inferred. It does not catch up a scheduled
notification missed while HA was stopped. Create one daily automation per desired
schedule/group; multiple automations may each send a notification.

## Grouped parcel alerts

The new parcel blueprint consumes `my_bpost_notification`. Raw parcel events and
native device triggers keep their earlier semantics. Existing blueprint files
are not overwritten automatically: replace the parcel YAML and reload
automations to adopt the new stream. Configure one automation with **all sources**
enabled for deduplicated household alerts. Leaving it disabled follows the
device owning the currently selected source, which may change over time.

Updates within a fixed 30-second window produce at most one notification per
parcel, using the final selected status. A status change takes priority over a
simultaneous ETA change. ETA-only alerts require a day change or a shift of at
least the configured `eta_change_minutes` (5–240, default 30), taken from the
selected entry. Small shifts accumulate from the last announced estimate.
An estimate appearing for the first time seeds a silent baseline. Missing
estimates are not rescheduling events.

Persisted baselines contain a hash of the tracking number, status and ETA, and
expire after 60 days without a relevant observation. They prevent repeated
announcements across reloads. Pending 30-second windows are not persisted; a
shutdown or crash can lose such a notification. This is best-effort notification
delivery, not an exactly-once queue. Quiet-hour events are skipped, not delayed;
the daily digest offers a separate morning view. No notification is sent until
you configure an automation and choose a phone.

## Tracking health

Each loaded account/manual entry exposes a diagnostic **Tracking health** sensor.
It remains readable when parcel refreshes fail: `ok`, `auth_required`,
`rate_limited`, `maintenance`, `outdated_client`, `not_found` or
`service_unavailable` (`starting` before the initial result).

Attributes include last attempt, last successful fetch, and the next rate-limit
retry time when known. Optional Mail Ahead capability and update health are
separate; courier capability distinguishes disabled, available and not currently
available. Public entries mark these account-only capabilities `unsupported`.
An absent courier round is not a parcel-service outage. These are observations,
not guarantees of upstream availability. Before the first successful setup,
Home Assistant's native setup/reauthentication message reports the failure.
