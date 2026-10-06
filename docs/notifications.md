# Notifications and automations

[Documentation](README.md) · [Project overview](../README.md)

## Blueprints

Three ready-to-configure blueprints are included under
[`blueprints/automation/my_bpost`](../blueprints/automation/my_bpost):

- [Parcel notifications](../blueprints/automation/my_bpost/parcel_notifications.yaml):
  choose delivery events, incoming/outgoing parcels, language and optional tracking
  details. Default notifications cover out-for-delivery, ready-to-collect,
  delivered and delivery problems.
- [New-letter notifications](../blueprints/automation/my_bpost/mail_notifications.yaml):
  notify when a new Mail Ahead letter is announced, without attaching scans or
  private image links.
- [Daily digest / pickup reminder](../blueprints/automation/my_bpost/daily_notifications.yaml):
  one summary at the chosen local time, optionally limited to a group or to days
  with parcels ready for collection. Counts only; no personal parcel details.

The current parcel/daily blueprints require My bpost 0.8.0b1+; letters require
0.6.0+. All require Home Assistant 2026.2.3+ and a phone/tablet registered
with the Home Assistant Companion app. Download the YAML assets from the same
release as the integration. Copy them to
`config/blueprints/automation/my_bpost/`, reload blueprints from the HA interface,
then create an automation. Select the receiving phone. For parcel alerts, choose
a My bpost device, then enable **all sources** in one automation to follow the
deduplicated stream across accounts and manual parcels. Without that switch,
the automation follows only events whose selected source belongs to that device.
You can also import a blueprint using the GitHub file URL for your installed
release tag in HA’s **Import blueprint** dialog.

Notifications support FR/EN/NL/DE and open the dashboard path you choose. Tracking
details are off by default; sender names and addresses are never included.
An opaque per-parcel tag lets updates replace that parcel's notification across
sources; letters retain account-specific tags. Parcel updates within 30 seconds
are grouped into one final observation. ETA alerts require a material change
(default 30 minutes, configurable in entry options); small shifts accumulate.
The baseline survives restart. Phone push behavior still depends on Companion
and the OS. Update existing blueprint copies and reload automations to use the
new stream; custom raw-event automations keep their existing behavior.

Quiet hours are optional and use HA's configured timezone. They can cross midnight;
the start is inclusive and the end exclusive. Equal start/end times disable the
quiet period. Events during quiet hours are **skipped**, not queued for the morning.
No automation or phone notification is enabled merely by installing the integration.

See [daily workflows](daily-workflows.md) for bulk import, management actions,
health states, summary fields and notification delivery limits.

## Device triggers

In an automation, choose **Device → My bpost** and select a trigger:

| Trigger | Event |
| --- | --- |
| New parcel | `my_bpost_new_package` |
| Status changed | `my_bpost_status_changed` |
| Out for delivery | `my_bpost_out_for_delivery` |
| Delivered | `my_bpost_delivered` |
| Ready to collect | `my_bpost_at_pickup_point` |
| Returned to sender | `my_bpost_returned` |
| Delivery problem | `my_bpost_problem` |
| Estimated delivery window changed | `my_bpost_eta_changed` |
| New letter announced | `my_bpost_letter_announced` |

Device triggers filter events to the selected account. Parcel information is in
`trigger.event.data`, including `item_code`, `status`, `entry_id` and `direction`.
The initial account import is silent; repeated identical statuses are suppressed.
ETA changes compare the account API's date/window, independently of live courier
polling. The first ETA and a missing date do not fire this trigger. A changed
existing estimate includes `old_eta` and `new_eta`, each `[day, start, end]`.
That baseline persists across restarts and temporary gaps.

Device triggers and raw events remain per source. For cross-source deduplication
and material ETA thresholds, use the parcel blueprint and
[grouped notification stream](daily-workflows.md#grouped-parcel-alerts).
Letter event fields are documented under [Mail Ahead](mail-ahead.md#new-letter-automation).
