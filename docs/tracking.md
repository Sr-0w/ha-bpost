# Parcels and tracking

[Documentation](README.md) · [Project overview](../README.md)

## Track a parcel without an account

Add **My bpost** in Devices & Services and choose **Track a parcel without an
account**. Enter the barcode, delivery postal code, optional display name and
language. The public API validates the pair before saving it. A newly created
shipping label may not be searchable yet; retry once bpost has announced it.

Each manual parcel is a separate integration entry. Its sensor, delivery calendar
and supplied pickup location appear alongside account parcels in the card. In
the entry's options you can edit the postal code, display name, direction and
retention. Incoming/outgoing direction is unspecified until you choose it:
knowing a barcode does not establish whether you are the sender or recipient.
Choose **Delete** on that integration entry to stop tracking and remove its
entities; this does not change the parcel in bpost or another account entry.

Public entries poll every 15 minutes while active and hourly after delivery or
return, respecting HTTP 429 pauses. Outages or a temporarily missing lookup make
entities unavailable while preserving the entry for retry. Delivered/returned
parcel entities use the same retention policy (7 days by default). The entry
remains until you delete it. A real process restart preserves identities and
announcement history. Tracking a parcel that is also in an account creates two
independent sources. In 0.8.0 the card, daily summary and grouped notification
stream deduplicate matching barcodes. Entity IDs and raw device triggers remain
independent. See [daily workflows](daily-workflows.md) for source selection.

No account tokens, client key or cookies are sent to public tracking. The barcode
and postal code are stored locally in HA and sent to `track.bpost.cloud`; protect
HA configuration and backups. Diagnostics redact these inputs and display names.
Mail Ahead and live courier GPS/stops are account-only features. Public entries
provide eight parcel device triggers and work with the parcel notification
blueprint; they do not provide letter triggers or image entities.

## Entities

| Entity | Description |
|---|---|
| `sensor.my_bpost_packages` | Number of active parcels (+ totals, codes, last fetch) |
| `sensor.my_bpost_<sender>` | One per parcel; state = status, attributes = sender, cities, ETA, last event, pickup point, history |
| `device_tracker.my_bpost_<sender>` | Present when coordinates are available |
| `calendar.my_bpost_deliveries` | Upcoming delivery estimates for this account (read-only) |
| Tracking health sensor | Refresh status, last success and retry information; [health reference](daily-workflows.md#tracking-health) |
| Mail Ahead status sensor | Available, not subscribed, not eligible, unknown or disabled |
| Letters (30 days) sensor | Letters in the available rolling window; unavailable when it cannot be read |
| Letter image entities | Optional scans fetched when viewed, through Home Assistant's image proxy |

Entity IDs are examples; Home Assistant may translate names or add a suffix.

Additional incoming/outgoing counters count active parcels with a known account
role. A parcel missing role data remains in the global count. Courier trackers
are separate from pickup locations and appear only after valid live coordinates
have been received.

Account polling adapts to activity: 30 minutes without active parcels, 10 minutes
in transit, and 5 minutes when a parcel is out for delivery. Automations can trigger on the
[`my_bpost_*` events](notifications.md#device-triggers) (payloads carry the parcel code and statuses).

## Parcel statuses

Parcel states are `registered`, `in_transit`, `out_for_delivery`,
`at_pickup_point`, `delivered`, `returning`, `returned`, `problem`, or `unknown`.
The original API value remains available in `raw_status`. An inactive parcel is not assumed delivered. Returns
to the sender use `returned`, not `delivered`.

## Parcel retention

Configure **Days to keep inactive parcels** under Settings → Devices & Services →
My bpost → Configure. The default is 7 days; the supported range is 1–365 days.
The clock starts when the integration first observes that a parcel is inactive
or absent from a successful account refresh. Existing history receives the same
grace period when upgrading. Active parcels are always kept.

After that period, the next successful account refresh removes the parcel sensor
and its pickup/courier trackers from Home Assistant's entity registry and the card.
The inactivity clock survives restarts. Historical parcels still returned by bpost
remain hidden; a parcel that becomes active again can be discovered again.
Temporary API failures do not purge entities. Account counters, calendars and
other accounts are preserved. This does not delete parcels from bpost or erase
Recorder history; Recorder keeps its own retention policy.

## Delivery calendar

Each account exposes a read-only **Deliveries** calendar usable in calendar cards,
the calendar view and calendar automations. Active parcels with a dated estimate
appear once. An updated estimate moves the same event; completed deliveries leave
the calendar. No extra API polling is needed.

Complete valid windows use Belgian local time (`Europe/Brussels`, including
daylight saving). A date with missing, invalid or reversed times becomes an all-day
event. Missing or unparseable dates produce no event; supported date formats are
`YYYY-MM-DD`, `DD/MM/YYYY` and `DD-MM-YYYY`. These are estimates, not appointments
confirmed by bpost. Calendar entries contain parcel labels and tracking numbers,
so only share this calendar with people who should see those details.

## Live delivery

Live tracking is enabled by default and can be disabled through the integration's
Configure dialog. It requires an active, recognized out-for-delivery parcel and
a recipient postcode supplied by the account API. No postcode is guessed from
the pickup point or sender.

Live requests are separate from account discovery, limited to two requests per
account in a rolling minute and at least 60 seconds between requests for one
parcel. Longer server intervals and HTTP 429 `Retry-After` are respected; missing
data and errors back off. Live observations expire after twice the requested
interval, bounded between two and ten minutes. An expired courier tracker becomes
unavailable and loses its coordinates; pickup coordinates are never substituted.

The card displays the supplied ETA, remaining stops (including a real zero), and
observation time. Its map button opens Home Assistant's native courier entity
details. Optional `account_id` and `direction: incoming | outgoing | all` settings
filter the card. The card also discovers renamed entities through their integration
attributes. API text is escaped before rendering.

Live fields depend on bpost's backend; an active delivery does not guarantee
courier data. Real courier payloads remain a [validation limit](distribution-validation.md#current-limits). `live_progress_raw` is exposed without assuming
percentage units, and no progress bar is shown until those units are verified.
