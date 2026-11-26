"""Tests for dose matching, take-all, repeats, schedules and storage."""

from datetime import timedelta

import pytest

from conftest import add, at, run, set_now


def snap(manager, medication_id="med_a"):
    return manager.get_snapshot(medication_id)


# ---------------------------------------------------------------- matching


def test_early_dose_counts_for_next_occurrence(manager):
    add(manager)
    # Yesterday and the day before were taken on time.
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
    set_now(at(7, 30))
    run(manager.async_log_dose("med_a", at(7, 30), allow_duplicate=True))
    set_now(at(9, 30))
    s = snap(manager)
    assert s["taken_today"] == 1
    assert s["outstanding"] is False
    assert s["missed_doses"] == 0


def test_late_dose_counts_for_the_right_occurrence(manager):
    add(manager, schedules=("08:00", "20:00"))
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 5, day), allow_duplicate=True))
        run(manager.async_log_dose("med_a", at(20, 5, day), allow_duplicate=True))
    set_now(at(10, 0))
    assert snap(manager)["outstanding"] is True
    run(manager.async_log_dose("med_a", at(10, 0), allow_duplicate=True))
    s = snap(manager)
    assert s["outstanding"] is False
    assert s["taken_today"] == 1
    assert s["missed_doses"] == 0


def test_dose_after_midnight_counts_for_evening_slot(manager):
    add(manager, schedules=("20:00",))
    run(manager.async_log_dose("med_a", at(20, 5, 24), allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(20, 5, 25), allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(0, 30, 27), allow_duplicate=True))  # for the 26th
    set_now(at(0, 40, 27))
    assert snap(manager)["missed_doses"] == 0


def test_old_missed_dose_counts_but_does_not_flag_recent(manager):
    add(manager, schedules=("20:00",))
    run(manager.async_log_dose("med_a", at(20, 5, 24), allow_duplicate=True))
    # the 25th is never taken; the 26th is taken
    run(manager.async_log_dose("med_a", at(20, 5, 26), allow_duplicate=True))
    set_now(at(9, 0, 27))
    s = snap(manager)
    assert s["missed_doses"] == 1  # the 25th
    assert s["recent_missed"] is False  # that was well over 24 hours ago


def test_missed_dose_within_a_day_flags_recent(manager):
    add(manager, schedules=("20:00",))
    run(manager.async_log_dose("med_a", at(20, 5, 24), allow_duplicate=True))
    set_now(at(9, 0))  # the 25th at 20:00 was 13 hours ago and never taken
    s = snap(manager)
    assert s["missed_doses"] == 1
    assert s["recent_missed"] is True


def test_recent_missed_flag_only_for_last_day(manager):
    add(manager, schedules=("08:00",))
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(8, 0, 25), allow_duplicate=True))
    set_now(at(10, 0))  # 26th at 08:00 never taken and the 60 minute threshold has passed
    s = snap(manager)
    assert s["recent_missed"] is True
    assert s["outstanding"] is True
    run(manager.async_log_dose("med_a", at(10, 0), allow_duplicate=True))
    assert snap(manager)["recent_missed"] is False


def test_new_medication_does_not_count_earlier_doses_today_as_missed(manager):
    set_now(at(14, 0))
    run(
        manager.async_add_medication(
            profile_id="mike",
            profile_name="Mike",
            medication_id="fresh",
            medication_name="Fresh",
            dosage="1",
            schedules=["08:00", "20:00"],
        )
    )
    set_now(at(14, 5))
    s = snap(manager, "fresh")
    assert s["missed_doses"] == 0
    assert s["outstanding"] is False


def test_skipped_occurrence_is_not_missed_or_outstanding(manager):
    add(manager)
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(8, 0, 25), allow_duplicate=True))
    set_now(at(9, 0))
    run(manager.async_skip_medication_occurrence("med_a"))
    s = snap(manager)
    assert s["outstanding"] is False
    assert s["missed_doses"] == 0


# ---------------------------------------------------------------- take all


def test_take_all_logs_everything_due_and_only_once(manager):
    add(manager, "med_a", "Vitamin D")
    add(manager, "med_b", "Omega 3")
    add(manager, "med_c", "Dog pill", profile="Rex")
    set_now(at(8, 5))
    result = run(manager.async_log_outstanding(profile_id="mike", source="test"))
    assert sorted(result["logged"]) == ["med_a", "med_b"]
    assert snap(manager, "med_c")["outstanding"] is True  # other profile untouched
    again = run(manager.async_log_outstanding(profile_id="mike", source="test"))
    assert again["logged"] == []
    everything = run(manager.async_log_outstanding(source="test"))
    assert everything["logged"] == ["med_c"]


def test_take_all_respects_duplicate_guard(manager):
    add(manager, "med_a", duplicate_guard_minutes=60)
    run(manager.async_log_dose("med_a", at(8, 0, 25), allow_duplicate=True))
    set_now(at(8, 1))
    run(manager.async_log_dose("med_a", at(8, 0), allow_duplicate=True))
    # taken, so nothing outstanding
    assert run(manager.async_log_outstanding())["logged"] == []


# ---------------------------------------------------------------- repeats


def _pending(manager):
    return [a for a in manager.get_pending_alerts() if a["type"] == "due"]


def test_reminder_repeats_then_stops(manager):
    add(manager, repeat_every_minutes=5, max_repeats=2)
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
    set_now(at(8, 0))
    alerts = _pending(manager)
    assert len(alerts) == 1 and alerts[0]["repeat"] is False
    run(manager.async_mark_alert_sent("med_a", "due", alerts[0]["scheduled_time"]))

    set_now(at(8, 1))
    assert _pending(manager) == []

    sent = 1
    for minute in (5, 10):
        set_now(at(8, minute))
        alerts = _pending(manager)
        assert len(alerts) == 1, minute
        assert alerts[0]["repeat"] is True
        assert alerts[0]["message"].startswith("Reminder:")
        run(manager.async_mark_alert_sent("med_a", "due", alerts[0]["scheduled_time"]))
        sent += 1
    assert sent == 3
    set_now(at(8, 14))
    assert _pending(manager) == []  # 1 original + 2 repeats, that's it


def test_no_repeats_when_disabled(manager):
    add(manager, repeat_every_minutes=0)
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
    alerts = _pending(manager)
    run(manager.async_mark_alert_sent("med_a", "due", alerts[0]["scheduled_time"]))
    set_now(at(8, 10))
    assert _pending(manager) == []


def test_logging_a_dose_stops_reminders(manager):
    add(manager)
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
    alerts = _pending(manager)
    run(manager.async_mark_alert_sent("med_a", "due", alerts[0]["scheduled_time"]))
    set_now(at(8, 6))
    run(manager.async_log_dose("med_a", at(8, 6), allow_duplicate=True))
    set_now(at(8, 11))
    assert _pending(manager) == []


# ---------------------------------------------------------------- actions


def test_single_medication_actions(manager):
    add(manager)
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
    actions = _pending(manager)[0]["actions"]
    assert [a["title"] for a in actions] == ["Taken", "Snooze 10 min", "Skip"]
    assert actions[0]["action"] == "MEDICATION_CONFIRMED_med_a"


def test_grouped_actions_include_all_taken_and_respect_android_limit(manager):
    for ident in ("med_a", "med_b", "med_c"):
        add(manager, ident, ident.upper())
        for day in (24, 25):
            run(manager.async_log_dose(ident, at(8, 0, day), allow_duplicate=True))
    alerts = _pending(manager)
    assert len(alerts) == 1
    actions = alerts[0]["actions"]
    assert len(actions) == 3
    assert actions[0] == {"action": "MEDICATION_ALL_mike", "title": "All taken"}


# ---------------------------------------------------------------- schedules


def test_days_of_week(manager):
    add(manager, days_of_week=[0])  # Mondays only; the 26th is a Thursday
    set_now(at(9, 0))
    s = snap(manager)
    assert s["expected_doses_today"] == 0
    assert s["outstanding"] is False
    assert s["next_dose"].startswith("2026-11-30T08:00")
    assert manager.get_today_doses() == []


def test_all_seven_days_means_every_day(manager):
    med = add(manager, days_of_week=[0, 1, 2, 3, 4, 5, 6])
    assert med.days_of_week is None


def test_invalid_schedule_rejected(manager):
    with pytest.raises(Exception):
        add(manager, schedules=("25:99",))


# ---------------------------------------------------------------- doses and stock


def test_delete_dose_restores_stock(manager):
    add(manager, quantity=10)
    run(manager.async_log_dose("med_a", at(8, 0), allow_duplicate=True))
    assert manager.medications["med_a"].quantity == 9
    stamp = manager.medications["med_a"].dose_logs[-1].taken_at.isoformat()
    run(manager.async_delete_dose("med_a", stamp))
    assert manager.medications["med_a"].quantity == 10
    assert manager.medications["med_a"].dose_logs == []
    with pytest.raises(Exception):
        run(manager.async_delete_dose("med_a", stamp))


def test_reset_history_clears_missed(manager):
    add(manager)
    set_now(at(9, 30))
    assert snap(manager)["missed_doses"] > 0
    run(manager.async_reset_history("med_a"))
    assert snap(manager)["missed_doses"] == 0


# ---------------------------------------------------------------- settings, tags, storage


def test_default_notify_service_used_when_medication_has_none(manager):
    add(manager)
    add(manager, "med_b", notify_service="notify.mobile_app_other")
    run(manager.async_update_settings({"default_notify_service": "notify.mobile_app_mike_s24"}))
    assert snap(manager, "med_a")["effective_notify_service"] == "notify.mobile_app_mike_s24"
    assert snap(manager, "med_b")["effective_notify_service"] == "notify.mobile_app_other"


def test_unknown_setting_rejected(manager):
    with pytest.raises(Exception):
        run(manager.async_update_settings({"nope": 1}))


def test_tag_resolution(manager):
    add(manager, nfc_tag_id="tag-med")
    run(manager.async_update_settings({"all_tag_ids": ["tag-all"], "profile_tags": {"tag-mike": "mike"}}))
    assert manager.resolve_tag("tag-med")[0] == "medication"
    assert manager.resolve_tag("tag-all") == ("all", None)
    assert manager.resolve_tag("tag-mike") == ("profile", "mike")
    assert manager.resolve_tag("other") is None


def test_state_survives_restart(hass, manager):
    from mt.manager import MedicationTrackerManager

    add(manager, nfc_tag_id="t1", days_of_week=[1, 3], quantity=5)
    run(manager.async_update_settings({"default_notify_service": "notify.x", "all_tag_ids": ["a"]}))
    run(manager.async_log_dose("med_a", at(8, 0), allow_duplicate=True))
    fresh = MedicationTrackerManager(hass)
    run(fresh.async_initialize())
    med = fresh.medications["med_a"]
    assert med.days_of_week == [1, 3] and med.nfc_tag_id == "t1" and med.quantity == 4
    assert len(med.dose_logs) == 1
    assert fresh.settings["default_notify_service"] == "notify.x"
    assert fresh.settings["all_tag_ids"] == ["a"]


def test_loads_data_saved_by_the_old_version(hass):
    from mt.manager import MedicationTrackerManager

    hass.storage["medication_tracker"] = {
        "medications": [
            {
                "medication_id": "old",
                "profile_id": "mike",
                "profile_name": "Mike",
                "name": "Old",
                "dosage": "1",
                "schedules": ["08:00"],
                "start_date": "2026-01-01",
                "dose_logs": [{"taken_at": "2026-01-01T08:00:00+00:00", "source": "manual", "confirmed_by": None}],
            }
        ]
    }
    mgr = MedicationTrackerManager(hass)
    run(mgr.async_initialize())
    med = mgr.medications["old"]
    assert med.repeat_every_minutes == 5 and med.max_repeats == 2 and med.days_of_week is None
    assert mgr.settings["default_notify_service"] is None
    snap(mgr, "old")  # must not raise
