# Medication Tracker

Medication Tracker is a Home Assistant custom integration aimed at becoming a proper HACS-ready medication management system instead of a pile of YAML automations.

## What it does now

- Persistent medication records stored inside Home Assistant
- Multiple people or pets via `profile_id` and `profile_name`
- Backend-first medication management through the integration options UI
- Bundled starter medication database for common medications
- Daily scheduled doses using one or more `HH:MM` schedule times
- Sensors for next dose, last dose, missed doses, days remaining, and compliance percentage
- Binary sensors for `due now`, `needs refill`, and `has missed dose`
- Per-medication `Log Dose` buttons for Lovelace and device pages
- Due, missed-dose, and refill alerts with persistent notifications
- Optional actionable mobile notifications if you set a `notify` service per medication
- NFC tag confirmation by listening for Home Assistant `tag_scanned` events
- Assist intents for asking whether a medication was taken and for logging a dose by voice

## Installation

1. Add this repository as a custom repository in HACS.
2. Install `Medication Tracker`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & services`.

## Managing medications

The preferred admin path is now the backend UI:

1. Open `Settings -> Devices & services`.
2. Open `Medication Tracker`.
3. Choose `Configure`.
4. Add, edit, or remove medications from the options flow.

When adding a medication you can:

- Pick a bundled medication template from the built-in catalog
- Set one or more schedule times
- Enable or disable notifications
- Add a `notify` service like `notify.mobile_app_pixel_9` for actionable mobile alerts
- Link an NFC tag ID for tap-to-log support
- Set refill thresholds and due/missed alert timing windows

## Services

Services are still available for automations and advanced use:

- `medication_tracker.add_medication`
- `medication_tracker.log_dose`
- `medication_tracker.refill_medication`
- `medication_tracker.remove_medication`

## Assist

Example phrases:

- `Did I take Vitamin D`
- `When is the next dose of Vitamin D`
- `Log Vitamin D as taken`

## NFC

Set an `nfc_tag_id` on a medication. When Home Assistant fires a `tag_scanned` event with the same tag ID, the integration logs the dose automatically.

## Alerts and automations

The integration now:

- Creates persistent notifications for due, missed, and refill states
- Fires these events for your own automations:
  - `medication_tracker_dose_due`
  - `medication_tracker_dose_missed`
  - `medication_tracker_refill_needed`
  - `medication_tracker_nfc_logged`

If a medication has a `notify_service` configured, the integration also sends a mobile notification with a `Taken` action button.

There is also an example package at [examples/packages/medication_tracker_notifications.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/packages/medication_tracker_notifications.yaml) if you want to build your own event-driven notification flow.

## Lovelace

A starter dashboard example lives at [examples/lovelace/medication_tracker_dashboard.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/lovelace/medication_tracker_dashboard.yaml).

The integration also creates summary sensors for dashboard use:

- `sensor.medication_tracker_medication_count`
- `sensor.medication_tracker_due_now_count`
- `sensor.medication_tracker_missed_dose_count`
- `sensor.medication_tracker_refill_needed_count`
- `sensor.medication_tracker_next_due`

## Notes

This is already a solid first product slice, but there is still room to grow:

- richer medication database data
- dedicated Lovelace card(s)
- better schedule editing UX
- compliance history/report exports
- caregiver workflows and approvals
