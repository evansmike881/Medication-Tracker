"""Constants for the Medication Tracker integration."""

from __future__ import annotations

DOMAIN = "medication_tracker"
PLATFORMS = ["binary_sensor", "button", "sensor"]
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
SIGNAL_MEDICATIONS_UPDATED = f"{DOMAIN}_medications_updated"
SIGNAL_ALERTS_UPDATED = f"{DOMAIN}_alerts_updated"

EVENT_DOSE_DUE = f"{DOMAIN}_dose_due"
EVENT_DOSE_MISSED = f"{DOMAIN}_dose_missed"
EVENT_REFILL_NEEDED = f"{DOMAIN}_refill_needed"
EVENT_NFC_LOGGED = f"{DOMAIN}_nfc_logged"
EVENT_CAREGIVER_CONFIRMATION = f"{DOMAIN}_caregiver_confirmation"

CONF_PROFILES = "profiles"
CONF_MEDICATIONS = "medications"

ATTR_ACTION = "action"
ATTR_ALERT = "alert"
ATTR_DAYS_REMAINING = "days_remaining"
ATTR_CAREGIVER_NAME = "caregiver_name"
ATTR_CAREGIVER_NOTIFY_SERVICE = "caregiver_notify_service"
ATTR_CAREGIVER_CONFIRMATION_NEEDED = "caregiver_confirmation_needed"
ATTR_CONFIRMATION_REQUIRED = "confirmation_required"
ATTR_CONFIRMED_BY = "confirmed_by"
ATTR_FORM = "form"
ATTR_DOSE_COUNT = "dose_count"
ATTR_DOSAGE = "dosage"
ATTR_ENTITY_BASE = "entity_base"
ATTR_EXPECTED_DOSES_TODAY = "expected_doses_today"
ATTR_INSTRUCTIONS = "instructions"
ATTR_LAST_TAKEN = "last_taken"
ATTR_LAST_CONFIRMED_BY = "last_confirmed_by"
ATTR_MEDICATION_ID = "medication_id"
ATTR_MEDICATION_NAME = "medication_name"
ATTR_MISSED_DOSES = "missed_doses"
ATTR_NEXT_DOSE = "next_dose"
ATTR_NFC_TAG_ID = "nfc_tag_id"
ATTR_NOTES = "notes"
ATTR_NOTIFICATION_ENABLED = "notification_enabled"
ATTR_NOTIFY_SERVICE = "notify_service"
ATTR_PROFILE_ID = "profile_id"
ATTR_PROFILE_NAME = "profile_name"
ATTR_QUANTITY = "quantity"
ATTR_PURPOSE = "purpose"
ATTR_REFILL_AT = "refill_at"
ATTR_REMAINING_QUANTITY = "remaining_quantity"
ATTR_REMINDER_MINUTES = "reminder_minutes"
ATTR_SCHEDULES = "schedules"
ATTR_SOURCE = "source"
ATTR_START_DATE = "start_date"
ATTR_STRENGTH_OPTIONS = "strength_options"
ATTR_TAKEN_AT = "taken_at"
ATTR_TAKEN_TODAY = "taken_today"
ATTR_DATABASE_ENTRY_ID = "database_entry_id"
ATTR_MISSED_AFTER_MINUTES = "missed_after_minutes"
ATTR_NOTIFICATION_MESSAGE = "notification_message"
ATTR_SCHEDULED_TIME = "scheduled_time"

DEFAULT_SCAN_INTERVAL_MINUTES = 1
DEFAULT_REMINDER_MINUTES = 15
DEFAULT_MISSED_AFTER_MINUTES = 60
