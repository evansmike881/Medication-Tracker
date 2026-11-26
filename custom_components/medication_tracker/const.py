"""Constants for the Medication Tracker integration."""

from __future__ import annotations

DOMAIN = "medication_tracker"
VERSION = "0.3.0"
PLATFORMS = ["binary_sensor", "button", "calendar", "sensor"]
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
SIGNAL_MEDICATIONS_UPDATED = f"{DOMAIN}_medications_updated"
SIGNAL_ALERTS_UPDATED = f"{DOMAIN}_alerts_updated"

EVENT_DOSE_DUE = f"{DOMAIN}_dose_due"
EVENT_DOSE_MISSED = f"{DOMAIN}_dose_missed"
EVENT_REFILL_NEEDED = f"{DOMAIN}_refill_needed"
EVENT_NFC_LOGGED = f"{DOMAIN}_nfc_logged"
EVENT_CAREGIVER_CONFIRMATION = f"{DOMAIN}_caregiver_confirmation"
EVENT_DOSE_TAKEN = f"{DOMAIN}_dose_taken"

# Mobile app notification action prefixes.
ACTION_CONFIRMED_PREFIX = "MEDICATION_CONFIRMED_"
ACTION_ALL_PREFIX = "MEDICATION_ALL_"
ACTION_SNOOZE_PREFIX = "MEDICATION_SNOOZE_"
ACTION_SKIP_PREFIX = "MEDICATION_SKIP_"

# Sidebar panel and static assets.
PANEL_URL_PATH = "medication-tracker"
PANEL_COMPONENT = "medication-tracker-panel"
ASSET_BASE_URL = "/medication_tracker_assets"

# Entity unique-id keys, shared by the platforms and the registry clean-up.
MEDICATION_SENSOR_UNIQUE_KEYS = (
    "belongs_to",
    "next_dose",
    "last_taken",
    "missed_doses",
    "days_remaining",
    "compliance_percentage",
    "snoozed_until",
    "stock_depletion_date",
)
MEDICATION_BINARY_SENSOR_UNIQUE_KEYS = (
    "due_now",
    "needs_refill",
    "has_missed_dose",
    "caregiver_confirmation_needed",
)
MEDICATION_BUTTON_UNIQUE_KEYS = (
    "log_dose",
    "skip_dose",
    "snooze_10_minutes",
    "test_due_notification",
    "test_missed_notification",
    "test_refill_notification",
    "test_caregiver_notification",
)

CONF_PROFILES = "profiles"
CONF_MEDICATIONS = "medications"

ATTR_ACTION = "action"
ATTR_ALERT = "alert"
ATTR_BELONGS_TO = "belongs_to"
ATTR_DAYS_REMAINING = "days_remaining"
ATTR_CAREGIVER_NAME = "caregiver_name"
ATTR_CAREGIVER_NOTIFY_SERVICE = "caregiver_notify_service"
ATTR_CAREGIVER_CONFIRMATION_NEEDED = "caregiver_confirmation_needed"
ATTR_CONFIRMATION_REQUIRED = "confirmation_required"
ATTR_CONFIRMED_BY = "confirmed_by"
ATTR_DUPLICATE_GUARD_MINUTES = "duplicate_guard_minutes"
ATTR_DUPLICATE_DOSE_WARNING = "duplicate_dose_warning"
ATTR_FORM = "form"
ATTR_DOSE_COUNT = "dose_count"
ATTR_DOSAGE = "dosage"
ATTR_ENTITY_BASE = "entity_base"
ATTR_EXPECTED_DOSES_TODAY = "expected_doses_today"
ATTR_INSTRUCTIONS = "instructions"
ATTR_LAST_TAKEN = "last_taken"
ATTR_LAST_CONFIRMED_BY = "last_confirmed_by"
ATTR_MEDICATION_ID = "medication_id"
ATTR_MEDICATION_IDS = "medication_ids"
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
ATTR_SKIPPED_OCCURRENCES = "skipped_occurrences"
ATTR_SNOOZED_UNTIL = "snoozed_until"
ATTR_STOCK_DEPLETION_DATE = "stock_depletion_date"
ATTR_STOCK_STATUS = "stock_status"
ATTR_DAYS_OF_WEEK = "days_of_week"
ATTR_REPEAT_EVERY_MINUTES = "repeat_every_minutes"
ATTR_MAX_REPEATS = "max_repeats"
ATTR_PROFILE_IDS = "profile_ids"

DEFAULT_SCAN_INTERVAL_MINUTES = 1
DEFAULT_REMINDER_MINUTES = 15
DEFAULT_MISSED_AFTER_MINUTES = 60
DEFAULT_REPEAT_EVERY_MINUTES = 5
DEFAULT_MAX_REPEATS = 2

# A dose logged up to this long before a scheduled time still counts for it.
EARLY_WINDOW_MINUTES = 120

# Integration-wide settings (stored alongside the medications).
SETTING_DEFAULT_NOTIFY = "default_notify_service"
SETTING_FALLBACK_NOTIFY = "fallback_notify_service"
SETTING_ALL_TAG_IDS = "all_tag_ids"
SETTING_PROFILE_TAGS = "profile_tags"
DEFAULT_SETTINGS = {
    SETTING_DEFAULT_NOTIFY: None,
    SETTING_FALLBACK_NOTIFY: None,
    SETTING_ALL_TAG_IDS: [],
    SETTING_PROFILE_TAGS: {},
}
