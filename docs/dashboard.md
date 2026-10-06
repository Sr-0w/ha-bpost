# Dashboard card

[Documentation](README.md) · [Project overview](../README.md)

The integration ships a generic parcels card (auto-registered, no manual
resource needed). It follows the default Home Assistant theme as well as
any theme applied to the card, and is available in the card picker as
**Bpost Parcels**:

```yaml
type: custom:my-bpost-parcels-card
title: Parcels
show_history: true # also list delivered parcels (default: false)
```

| Default theme | Themed card |
|---|---|
| ![Bpost Parcels card, default theme](../images/card-default.png) | ![Bpost Parcels card, themed](../images/card-themed.png) |

*(Screenshots rendered with fictional demo data.)*

The [Today view and summaries](daily-workflows.md#today-view-and-private-summaries)
guide explains date handling, groups and duplicate selection.

## Visual editor

Edit the **Bpost Parcels** card in a dashboard to choose a title, account,
incoming/outgoing filter, Today view, group, duplicate filtering, sort order,
inactive history, live section and discreet mode without writing YAML. Account
labels use integration entry titles when available. A temporarily unavailable
selected account stays selected.

| Option | Default | Behavior |
| --- | --- | --- |
| `account_id` | All accounts | Limits the card to the selected account |
| `view` | `all` | `today` groups deliveries expected today, pickups and problems |
| `group` | All groups | Exact group name configured on the entry |
| `deduplicate` | `true` | One observation per exact tracking number, after filters |
| `direction` | `all` | `all`, `incoming` or `outgoing` |
| `sort_by` | `priority` | `priority`, `delivery_date`, `updated` or `name` |
| `show_history` | `false` | Includes inactive parcels still retained by the integration |
| `show_live` | `true` | Displays live information; hiding it does not stop API polling |
| `privacy_mode` | `false` | Shows numbered parcels and canonical statuses only |

Priority sorting puts delivery problems, ready-to-collect parcels and deliveries
in progress first. Invalid/missing dates sort last. Active parcels and history
remain separate. Discreet mode omits names, addresses, tracking IDs, events, ETA
and maps from the card's rendered HTML. It does not change HA entity data,
permissions, other cards or a custom title you choose yourself.
