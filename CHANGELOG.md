# Changelog

## 0.6.2

### Changed
- The four **Test ... Notification** buttons per medication are now disabled by default, which removes about 70 entities from a typical install. Enable one from the entity settings when you want to test. Buttons that already exist are not changed; disable them in Settings -> Entities if you do not want them.

## 0.6.1

### Fixed
- **Missed phone alerts.** If the phone notification could not be delivered (for example the Companion app was re-registering and its notify service did not exist), the alert was still marked as sent and never retried. Undelivered alerts are now retried every minute for up to two hours, or until the dose is taken or its window ends. The popup, announcement and event are only produced once; a repair issue still appears while delivery is failing, and clears when it works again.
- **Recorder warnings** about attributes over 16 KB on the summary and registry sensors. The large lists stay on the live state (the dashboard card still reads them) but are no longer written to the database.
- **Thread-safety error** (`loop ... is not the running loop`) when new entities were added after a signal sent from outside the event loop (sensors, binary sensors, buttons).

### Tip
Set a **fallback phone** in Settings so an alert can still reach a second device while the first is unavailable.

## 0.6.0

### Added
- **Collapsible groups** on the Medications tab (Collapse / Expand groups buttons) and on Today, where finished and upcoming groups fold away and the one that needs you is open as a checklist. Remembered per device.
- **Search** on the Medications tab.
- **Pause reminders** (holiday mode) for everyone or one person; paused days send nothing and never count as missed. Services `pause_reminders` and `resume_reminders`.
- **Per-person reminder phone** and a **weekly summary** notification (Settings -> People and weekly summary).
- **Food notes** (with food, on an empty stomach) and **keep apart from** (for example iron and calcium) with warnings in the panel and when doses are taken too close together.
- **Backup and restore** from Settings, plus an automatic daily backup file (last 14 kept) and a safety copy before any restore.
- **Large-buttons mode** for tablets and touch screens.
- **Print report** for appointments, **Copy medication**, starting-point lists in Quick add, **Add stock** buttons on the low-stock banner, folded-group drop targets, and a clear message when a medication is dropped on another person's group.
- Low-stock notifications now say about how many days are left.

### Changed
- Reminders and announcements now fall back person phone, then default phone, when a medication or group has none of its own.

### Upgrading
Nothing to migrate: 0.5.x data loads unchanged and the new settings start switched off. Restart Home Assistant and hard refresh the browser (Ctrl+Shift+R).

## 0.5.0

### Added
- **Groups.** Put several medications, vitamins or minerals in a group to get one notification, one spoken announcement and one Take all button, while each item is still tracked individually (history, stock, adherence, missed doses). A group has its own times, days, reminder phone, reminders switch and optional NFC tag.
- **Drag and drop** in the panel: move medications into and out of groups, reorder them, and reorder groups. Works with touch, mouse and the keyboard (arrow keys on a focused handle), and a Group dropdown on the medication form does the same thing without dragging.
- **Quick add several**: type a list (`Vitamin D, 1000 IU` per line) straight into a new or existing group.
- **Today as checklists**: group blocks with "2 of 5 taken", a progress bar and Take all; the dashboard card does the same.
- **Group notification actions**: All taken / Snooze 10 min for a group; a notification with several mixed items gets All taken and Snooze for the lot. Tapping a notification opens the panel so you can tick items individually.
- Services `add_group`, `remove_group`, `set_medication_group`; `group_id` on `add_medication` and `log_all_due`. Assist can log a group by name.

### Changed
- Several things due together at once now give one notification, titled by group when they belong to one.

### Upgrading
Nothing to migrate: 0.4.x data loads unchanged and nothing is grouped until you create a group. Restart Home Assistant and hard refresh the browser (Ctrl+Shift+R).

## 0.4.0

### Added
- **Alarm-style phone notifications** for due, missed and escalated doses: Android alarm channel, high priority, delivered immediately, and kept on screen until you act. Switch off under Settings if you prefer normal notifications. Refill reminders are always normal.
- **Spoken reminders**: pick a notify service that speaks (for example an Alexa Media `notify.alexa_media_*` service) and reminders are announced aloud. Optionally only when a person is home, and never during quiet hours.
- **Escalation**: if a dose is still not taken some minutes after it was due, tell a caregiver. Set per medication; goes to the medication's caregiver phone or the default escalation phone in Settings. The caregiver's notification has Mark taken / Skip buttons.
- **Quiet hours**: silence announcements and refill reminders overnight. Dose reminders to your phone are never silenced.
- **Taken earlier**: log a dose at the time you actually took it. **Undo** the last dose from the panel, the dashboard or the `undo_last_dose` service.
- **As-needed medication** with an optional daily limit (and a minimum gap using duplicate-dose protection). Shown in its own card with "1 of 4 today".
- **Courses**: an end date after which a medication stops reminding.
- **Every N days** schedules (every other day, weekly, fortnightly) with a chosen first day.
- **Who took it**: the Home Assistant user behind a panel tap, service call, NFC scan or notification button is recorded and shown in History and on the medication.
- **Adherence** per medication in the panel, plus **Export CSV** of the last 12 months.
- **Dashboard card** `custom:medication-tracker-today-card` (optional `title` and `profile`) with Taken and Take all due buttons.
- `medication_tracker_dose_escalated` event; `taken_by` on `medication_tracker_dose_taken`.
- GitHub Actions: unit tests and front-end syntax check on every push; hassfest and HACS validation (non-blocking at first).

### Changed
- Dose matching only looks back 12 months and logs older than two years are dropped on startup, so storage and processing stay small however long it runs.
- The notification toast in the panel no longer redraws the page, which could drop focus from a field you were typing in.
- Calendar and stock forecasts understand weekdays, intervals and as-needed medication.

### Upgrading
Nothing to migrate: stored data from 0.3.x loads unchanged. After updating, restart Home Assistant and do a hard refresh in the browser (Ctrl+Shift+R) so the new panel loads. New options live in the panel under Settings and on each medication's edit page.

## 0.3.0

### Fixed
- A notification service that is missing or misspelled (for example `notify.mobile_app_*` not loaded yet at startup) no longer aborts alert processing. Previously it skipped marking the alert as sent, so it retried every minute and never fired its event. Failures are now logged once, shown in Repairs, and an optional backup phone is tried.
- Persistent notifications were dismissed one minute after being created. They now stay until the dose is taken, skipped or the reminder window ends.
- Phone notifications are now cleared when a dose is logged by any route (previously only the in-app notification was cleared).
- Dose matching: a dose taken early, late or after midnight is now matched to the right scheduled slot instead of being counted as missed.
- A medication created part-way through the day no longer reports earlier slots that day as missed.
- `Has Missed Dose` was permanently on after a single missed dose. It now reflects the last 24 hours only.
- NFC scans and notification buttons no longer raise unhandled errors (for example when duplicate-dose protection blocks a log).
- Removing the integration now removes its services (the previous check never matched).
- The Lovelace card is registered under the `medication-tracker-cards-v3.js` path that existing dashboards reference, and loading it twice no longer throws.
- Blocking file access when installing the Assist sentences now runs in an executor; the deprecated device-registry iteration was replaced.
- `manifest.json` points at this repository and declares `after_dependencies` for `mobile_app`, `notify` and `tag`; `hacs.json` lists all platforms.
- The README's example link no longer points at a local network share.

### Added
- **Medications panel** in the sidebar: Today, Medications, History and Settings tabs.
- **Take all due** - service `log_all_due`, a button entity, notification action, Assist phrase, panel button, and NFC tags (everything / per person).
- Notification actions: Taken, Snooze 10 min, Skip, and All taken for grouped reminders.
- Repeat reminders (`repeat_every_minutes`, `max_repeats`).
- Days of the week per medication.
- Default and backup notify service in settings; one default instead of setting it on every medication.
- Services `delete_dose`, `reset_history`, `update_settings`; event `medication_tracker_dose_taken`.

### Upgrading
Stored data is backward compatible: existing medications and dose history load unchanged and gain sensible defaults. After installing, restart Home Assistant, open **Medications -> Settings** and choose your phone (for example `notify.mobile_app_mike_s24`). Use **Send test notification** on a medication's edit page to confirm it arrives.

If a medication shows old "missed" history you don't care about, open its edit page and press **Reset history**.
