# Medication Tracker

Medication Tracker is a Home Assistant integration built for one very real problem: remembering who took what, when they took it, and what still needs attention without relying on sticky notes, memory, or a mess of YAML automations.

I wanted this to feel like a proper product inside Home Assistant, not just a handful of scripts. The goal is simple: make medication routines easier to trust, easier to check, and easier to act on for yourself, your family, or your pets.

> [!WARNING]
> Medication Tracker is not medical advice, not a medical device, and must not be your only safeguard for medication routines. Always verify doses, timing, and instructions against professional guidance and the official medication packaging.

## Important disclaimer

Medication Tracker is provided for convenience, organization, and informational use only.

- It is not medical advice.
- It is not a medical device.
- It is not a substitute for professional medical guidance, prescription instructions, pharmacist advice, packaging directions, or clinical judgment.
- You must not rely on this integration as the sole safeguard for taking, supervising, confirming, or managing any medication.

By using this integration, the user, medication owner, caregiver, and household remain fully responsible for:

- correct medication identification
- dosing, timing, and administration
- refill management
- checking for missed, duplicated, delayed, or incorrect doses
- verifying alerts, logs, confirmations, and dashboard information
- following prescriber instructions and product labeling

This project may contain bugs, configuration mistakes, delayed notifications, missed automations, inaccurate state, frontend issues, entity problems, or logging errors. Notifications may fail, entities may not update as expected, and recorded data may be incomplete or incorrect.

Use of this integration is entirely at your own risk. The maintainers, contributors, and distributors of this project accept no responsibility for medication errors, missed doses, duplicate doses, adverse outcomes, data loss, notification failures, or any direct or indirect harm arising from use of the software.

If a medication routine is safety-critical, use additional safeguards and always confirm decisions against professional medical advice and the official medication instructions.

## Why this exists

Medication routines are one of those things that sound simple until life gets busy.

- Did I already take that this morning?
- Did someone miss an evening dose?
- Are we about to run out?
- What was the last time this was logged?
- Can I confirm it quickly without opening five different screens?

Medication Tracker is designed to answer those questions fast, inside the Home Assistant setup you already use every day.

## What makes it useful

- Track medications for multiple people or pets
- Create proper schedules with one or more dose times
- Log doses manually, from Lovelace, from NFC, or from Assist
- See next dose, last dose, missed doses, refill status, and compliance
- Get due, missed-dose, and refill alerts
- Use a built-in medication database to speed up setup
- Store richer medication reference details like purpose, form, instructions, and common strengths
- Manage everything from the Home Assistant backend instead of raw YAML
- Support caregiver-aware routines where someone else is responsible for checking or confirming doses

## What it feels like in practice

The experience I’m aiming for is:

- Add a person or pet in a friendly setup flow
- Pick a medication from the built-in list or create your own
- Choose the times it should be taken
- Let Home Assistant surface what is due, missed, or running low
- Tap one button to log a dose
- Open a single dashboard and understand the whole picture immediately

That means less second-guessing, fewer missed steps, and a much better shared view for households where more than one person is involved.

## Current features

- Persistent medication records stored inside Home Assistant
- Multiple people or pets via profile-based tracking
- Backend-first medication management through the integration options UI
- Bundled starter medication database for common medications
- Richer medication metadata including purpose, form, instructions, and strength options
- Daily scheduled doses with one or more times per day
- Sensors for ownership, next dose, last dose, missed doses, days remaining, and compliance percentage
- Binary sensors for `due now`, `needs refill`, and `has missed dose`
- Per-medication `Log Dose`, `Skip Dose`, `Snooze`, and notification test buttons
- Due, missed-dose, and refill alerts
- Smart grouped notifications for due, missed, refill, and caregiver alerts when multiple medications belong together
- Duplicate-dose protection with optional override for supervised/manual corrections
- Stock forecasting with projected depletion dates
- Real Home Assistant calendar entity support for scheduled medications
- Optional actionable mobile notifications using a `notify` service
- Optional caregiver name, caregiver notification target, and caregiver confirmation workflow
- NFC tag confirmation through Home Assistant `tag_scanned` events
- Assist intents for medication status and logging
- Summary sensors and a medication registry for dashboards
- A custom Lovelace card for a cleaner registry view

## Installation

1. Add this repository as a custom repository in HACS.
2. Install `Medication Tracker`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & services`.

## Managing medications

The preferred admin flow is built into Home Assistant:

1. Open `Settings -> Devices & services`
2. Open `Medication Tracker`
3. Choose `Configure`
4. Add, edit, or remove medications from the guided setup flow

The flow is designed to be friendly:

- choose an existing person or pet, or create a new one
- pick a medication template or use a custom medication
- enter the basics first
- choose schedule times with time pickers
- optionally add advanced settings like reminders, refill thresholds, NFC tags, and mobile notifications
- optionally assign a caregiver or responsible adult and require confirmation for supervised routines

## Dashboard and registry views

A starter dashboard example lives at [examples/lovelace/medication_tracker_dashboard.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/lovelace/medication_tracker_dashboard.yaml).

A dedicated registry-style dashboard example lives at [examples/lovelace/medication_registry_dashboard.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/lovelace/medication_registry_dashboard.yaml).

A calendar-style schedule example now also lives at [examples/lovelace/medication_calendar_dashboard.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/lovelace/medication_calendar_dashboard.yaml).

The integration also now exposes a real Home Assistant calendar entity that can be added to Calendar dashboards and used in calendar automations.

There is also a custom Lovelace card served by the integration:

```yaml
type: custom:medication-tracker-card
entity: sensor.medication_tracker_medication_registry
title: Medication Registry
```

The card now includes a visual editor in Lovelace so you can turn sections on or off without hand-editing YAML. You can also configure it manually if you prefer:

```yaml
type: custom:medication-tracker-card
entity: sensor.medication_tracker_medication_registry
title: Medication Registry
show_summary: true
show_status_chip: true
show_profile_name: true
show_dosage: true
show_caregiver: false
show_compliance: true
show_actions: true
compact_rows: false
max_rows: 6
```

There is also a second custom card for a more minimal weekly pill-box layout. It is designed for one selected person or pet and groups medications into seven day boxes:

```yaml
type: custom:medication-tracker-weekly-card
entity: sensor.medication_tracker_medication_registry
title: Weekly Pill Box
profile_name: Mike
show_summary: true
show_times: true
show_dosage: true
show_status_chip: true
show_actions: true
collapsible_items: true
expand_today: true
```

If the card does not appear immediately after updating, add it manually as a Lovelace resource:

```yaml
url: /medication_tracker_assets/medication-tracker-cards-v2.js
type: module
```

Then refresh the browser and add the card again.

## Alerts and automations

The integration can create persistent notifications and also fire events you can build automations around:

- `medication_tracker_dose_due`
- `medication_tracker_dose_missed`
- `medication_tracker_refill_needed`
- `medication_tracker_nfc_logged`

If a medication has a `notify_service` configured, Medication Tracker can also send actionable mobile notifications with `Taken` action buttons.

When more than one medication matches the same person or pet and notification target, the integration now combines related due, missed-dose, refill, and caregiver alerts into one structured notification with a medication list instead of sending one separate alert per medication.

If a medication has caregiver confirmation enabled, the integration can also raise caregiver confirmation alerts so household workflows are clearer when someone else is responsible for checking the dose.

Each medication device also exposes button entities you can press from Home Assistant to test due, missed-dose, refill, and caregiver confirmation notifications without waiting for a real schedule event.

An example notification package lives at [examples/packages/medication_tracker_notifications.yaml](//192.168.4.229/html/!HA%20Integrations/Medication%20Tracker/examples/packages/medication_tracker_notifications.yaml).

## Assist

Example phrases:

- `Did I take Vitamin D`
- `Have I taken omeprazole`
- `When is the next dose of Vitamin D`
- `When is omeprazole due`
- `What medications are due now`
- `What medications are running low`
- `Log Vitamin D as taken`
- `Has Mike taken omeprazole`
- `What does Bella need to take`
- `Does Mum need any refills`

Reliable Assist phrases:

- `Medication status for omeprazole`
- `Medication due list`
- `Medication due now for Mike`
- `Medication refill list`
- `Medication stock check for Bella`
- `Log medication omeprazole as taken`
- `Log medication omeprazole for Mike as taken`

## NFC

Set an `nfc_tag_id` on a medication and scan that tag to log the dose automatically.

## Services

The UI is the preferred way to manage medications, but services are still available for automations and power users:

- `medication_tracker.add_medication`
- `medication_tracker.log_dose`
- `medication_tracker.refill_medication`
- `medication_tracker.remove_medication`
- `medication_tracker.snooze_medication`
- `medication_tracker.skip_medication`

## Where this is heading

This already works as a serious Home Assistant integration, but I’m building it with a bigger vision in mind:

- richer medication database support
- better household and caregiver workflows
- cleaner dashboards and custom cards
- easier refill planning
- stronger history and reporting

## Final thought

Medication Tracker is meant to reduce friction around something important.

If it helps you avoid missed doses, reduce uncertainty, support someone you care about, or simply make your daily routine feel more reliable, then it is doing exactly what it was built to do.
