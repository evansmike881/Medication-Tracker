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

## Groups: one reminder for several medications

If you take a handful of prescriptions plus a pile of vitamins and minerals, you don't want a separate alert for each. Put them in a **group**:

- One notification (titled with the group name), one spoken announcement, and one **Take all** button for the whole group.
- Every medication inside is still tracked on its own: its own history, stock count, adherence and missed doses. Tick them one by one in the panel if you prefer.
- A group owns the times, days and reminder phone; members follow it. Change the group's time once and everything in it moves.
- Different people have separate groups, and as-needed medication is never grouped.
- A group can have its own NFC tag that marks everything due in it as taken, and you can say "log medication morning vitamins as taken" to Assist.

Quickest way to set up: **Medications -> Quick add several**, pick the person, choose "A new group", give it a name and a time, and type one medication per line (`Vitamin D, 1000 IU`). Then drag things around.

## Installation

1. Add this repository as a custom repository in HACS / the Home Assistant Marketplace (type: Integration).
2. Install `Medication Tracker`.
3. Restart Home Assistant.
4. Add the integration from `Settings -> Devices & services`.
5. Open the new **Medications** item in the sidebar, go to **Settings**, and pick the phone that should get reminders.

## The Medications panel

Medication Tracker adds a **Medications** page to the Home Assistant sidebar. It is the easiest way to use the integration day to day:

- **Today** - everything scheduled today with its status. Groups show as a checklist with a progress bar and a **Take all** button for the group; press **Take all due** to mark everything that is due as taken, **All taken for <person>** for one person, or Taken / Skip on a single medication.
- **Medications** - organised by person and group. **Drag the ⠿ handle** to move a medication into a group, out of one, or to reorder; drag a group's handle to reorder groups (touch, mouse, or focus a handle and use the up and down arrow keys). Add, edit, delete and top up stock. Pick times with time pickers, choose which days of the week, set how many doses you have left, and bind an NFC tag (press **Scan** and tap the tag with your phone).
- **History** - recent doses, with the option to delete one that was logged by mistake.
- **Settings** - default phone for reminders, a backup phone, and NFC tags that mark everything (or one person's medications) as taken.

Anyone can mark doses taken from the panel. Editing medications and settings is limited to Home Assistant administrators.

## More things it can do

- **Loud reminders** - due, missed and escalated doses use Android's alarm channel at high priority and stay on screen until you act (Settings -> Reminders to turn off).
- **Spoken reminders** - choose a notify service that speaks, such as an Alexa Media `notify.alexa_media_*` service. Optionally only when a person is home, and never during quiet hours.
- **Escalation** - on a medication's edit page, set "Tell caregiver if not taken after (min)". If the dose is still outstanding, the caregiver's phone (or the default escalation phone in Settings) gets a notification with Mark taken / Skip.
- **Quiet hours** - silence announcements and refill reminders overnight. Dose reminders to your phone are never silenced.
- **As-needed medication** - tick "As needed" for things like paracetamol. Set a daily limit and use "Block double-logging for" for the minimum gap between doses.
- **Courses** - set "Course ends" and the medication stops reminding after that day.
- **Every N days** - every other day, weekly or fortnightly, from a chosen first day.
- **Taken earlier / Undo** - log the time you actually took it, or undo the last dose.
- **Who took it** - recorded from the Home Assistant user, and shown in History.
- **Adherence and CSV export** - on the History tab.

### Dashboard card

```yaml
type: custom:medication-tracker-today-card
title: Medications     # optional
profile: mike          # optional - only this person (profile id)
```

## Managing medications (options flow)

The original guided setup flow still works too:

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
- `medication_tracker_dose_escalated` (a dose is still not taken after the escalation delay)
- `medication_tracker_dose_taken` (fired whenever dose(s) are logged, with the `source`: `panel`, `mobile_action`, `nfc`, `assist`, `button`, `manual`)

Reminders go to the phone chosen in the panel's Settings (or a medication's own `notify_service`). The notification has action buttons:

- one medication: **Taken**, **Snooze 10 min**, **Skip**
- several medications due together: **All taken** plus **Taken: <name>** for the first two (Android shows at most three buttons; the panel handles the rest)

Reminders repeat (default every 5 minutes, up to 2 more times) until the dose is taken, skipped or snoozed, and the notification disappears from your phone as soon as the dose is logged, from any route. If the notify service name is wrong or the phone is unreachable, a warning appears in `Settings -> System -> Repairs` and the failure is logged once instead of every minute.

Doses are matched to the schedule generously: a dose up to two hours early still counts for the next scheduled time, and a late dose counts for the slot it was meant for. A medication added mid-day does not report earlier slots that day as missed, and `Has Missed Dose` only turns on for doses missed in the last 24 hours.

When more than one medication matches the same person or pet and notification target, the integration now combines related due, missed-dose, refill, and caregiver alerts into one structured notification with a medication list instead of sending one separate alert per medication.

If a medication has caregiver confirmation enabled, the integration can also raise caregiver confirmation alerts so household workflows are clearer when someone else is responsible for checking the dose.

Each medication device also exposes button entities you can press from Home Assistant to test due, missed-dose, refill, and caregiver confirmation notifications without waiting for a real schedule event.

An example notification package lives at [examples/packages/medication_tracker_notifications.yaml](examples/packages/medication_tracker_notifications.yaml).

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
- `I took all my medications` / `Mark all medications as taken for Mike`

## NFC

Write a tag with the Home Assistant Companion app (`Settings -> Tags -> Create tag -> Write to NFC`), then:

- **One medication** - set the tag on the medication's edit page in the panel (press **Scan**, tap the tag). Scanning logs that dose.
- **A group** - set the tag on the group's edit page. Scanning marks everything currently due in that group as taken.
- **Everything due** - add the tag under `Settings -> NFC tags` in the panel. Scanning marks everything currently due as taken.
- **One person** - set a tag against a person in the same place. Scanning marks only that person's due medications as taken.

If nothing is due when an "everything" or "person" tag is scanned, no dose is logged and a notification says so.

## Services

The UI is the preferred way to manage medications, but services are still available for automations and power users:

- `medication_tracker.add_medication` (now also `days_of_week`, `repeat_every_minutes`, `max_repeats`)
- `medication_tracker.log_dose`
- `medication_tracker.log_all_due` (optionally `profile_id`, `group_id` or `medication_ids`)
- `medication_tracker.add_group`, `medication_tracker.remove_group`, `medication_tracker.set_medication_group`
- `medication_tracker.delete_dose`
- `medication_tracker.reset_history`
- `medication_tracker.update_settings`
- `medication_tracker.undo_last_dose`
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
