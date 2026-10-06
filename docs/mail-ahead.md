# Mail Ahead

[Documentation](README.md) · [Project overview](../README.md)

Mail Ahead checks the service's eligibility/subscription flags and fetches announced
letters for subscribed accounts. Enable the service in the official bpost app if
bpost makes it available to your account; this integration never subscribes you or
changes your account. **Mail Ahead status** distinguishes `available`,
`not_subscribed`, `not_eligible`, `unknown` and `disabled`.

**Letters (30 days)** counts distinct letters in the rolling 30-day window ending
today in Belgium. It is not a count of unread letters or letters arriving today.
An empty, successfully retrieved mailbox reads zero; unavailable access or an API
failure makes the sensor unavailable. Mail polling runs every 30 minutes when
available, every 12 hours otherwise. It respects rate limits and operates
independently of parcel updates. Disable it through **Configure → Enable Mail Ahead**.

## Letter images

Images are **off by default**. Enable **Configure → Enable letter images** to
create one native `image` entity per letter with a scan. Use these entities in
Home Assistant's picture-entity cards or their more-info dialogs. For example,
replace this entity with one offered by your account:

```yaml
type: picture-entity
entity: image.my_bpost_letter_2026_10_06
show_state: false
```

Images download only when viewed. Home Assistant serves them through its native
image proxy, which requires a logged-in session or a rotating HA image token.
Treat copied HA image links as private. Envelope scans can contain names and
addresses. The integration does not expose bpost's signed image URLs, senders,
raw letter identifiers or image references in entity attributes, events or diagnostics.
It stores neither scans nor signed links on disk; cached image bytes are reused
for at most 15 minutes and invalidated when references change or the mailbox fails.
Browser caches and snapshots explicitly requested through HA are separate.

Downloads use a separate session without bpost account headers/cookies, verified
HTTPS and no redirects. Supported hosts are bpost.be, bpost.cloud and their
subdomains, plus Azure Blob Storage (`*.blob.core.windows.net`). Only PNG, JPEG
and WebP scans up to 5 MiB are accepted. An unsupported image does not break
parcel tracking or the mail count. Image entities disappear after a successful
refresh removes their letter/scan, or when images are disabled.

## New-letter automation

The account device offers **New letter announced**, backed by
`my_bpost_letter_announced`. Its payload contains `entry_id`, an opaque `mail_id`,
`date` and optional `planned_delivery`. The first successful mailbox import is
silent. A persisted baseline of hashed IDs prevents repeated announcements after
restarts and temporary disappearance. Only hashes and last-seen timestamps are
stored; absent IDs expire from that baseline after 60 days of successful polling.

For a ready-made phone alert, use the [letter notification blueprint](notifications.md#blueprints).

Real populated mailboxes and scan hosts remain [validation limits](distribution-validation.md#current-limits).
Mail Ahead requires an eligible account; manually tracked public parcels do not
provide letters or scans.
