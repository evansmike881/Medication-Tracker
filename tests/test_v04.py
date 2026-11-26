"""Tests for 0.4.0: courses, as-needed, intervals, undo, taken_by, escalation, quiet hours,
alarm-style notifications, announcements and history limits."""

from datetime import date, timedelta

import pytest

from mt.const import EVENT_DOSE_ESCALATED

from conftest import ServiceNotFound, add, at, run, set_now


def snap(manager, medication_id="med_a"):
    return manager.get_snapshot(medication_id)


def prime(manager, ident="med_a", days=(24, 25), hour=8):
    for day in days:
        run(manager.async_log_dose(ident, at(hour, 0, day), allow_duplicate=True))


# ---------------------------------------------------------------- courses and intervals


def test_course_end_date_stops_schedule_and_reminders(manager):
    add(manager, end_date="2026-11-25")
    prime(manager)
    set_now(at(8, 0))
    s = snap(manager)
    assert s["course_ended"] is True
    assert s["expected_doses_today"] == 0
    assert s["next_dose"] is None
    assert manager.get_pending_alerts() == []
    assert manager.get_today_doses() == []


def test_end_date_can_be_cleared_and_invalid_rejected(manager):
    add(manager, end_date="2026-12-31")
    assert manager.medications["med_a"].end_date == date(2026, 12, 31)
    add(manager, end_date="")
    assert manager.medications["med_a"].end_date is None
    with pytest.raises(Exception):
        add(manager, end_date="not-a-date")


def test_every_other_day_schedule(manager):
    med = add(manager, interval_days=2, anchor_date="2026-11-24")
    # 24th and 26th are scheduled, 25th and 27th are not
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))
    set_now(at(9, 0, 25))
    assert manager.get_today_doses() == []
    assert snap(manager)["next_dose"].startswith("2026-11-26T08:00")
    set_now(at(8, 5, 26))
    assert len(manager.get_today_doses()) == 1
    assert snap(manager)["missed_doses"] == 0  # the 25th is simply not a dose day


def test_interval_validation(manager):
    with pytest.raises(Exception):
        add(manager, interval_days=0)
    with pytest.raises(Exception):
        add(manager, interval_days=99)


def test_days_remaining_accounts_for_interval(manager):
    add(manager, quantity=10, interval_days=2)
    assert snap(manager)["days_remaining"] == 20  # one dose every other day


# ---------------------------------------------------------------- as needed


def test_as_needed_has_no_schedule_or_reminders(manager):
    add(manager, schedules=(), as_needed=True, max_doses_per_day=2)
    s = snap(manager)
    assert s["as_needed"] is True
    assert s["next_dose"] is None and s["outstanding"] is False
    assert manager.get_pending_alerts() == []
    assert manager.get_today_doses() == []
    assert run(manager.async_log_outstanding())["logged"] == []  # take-all ignores it


def test_schedule_required_unless_as_needed(manager):
    with pytest.raises(Exception):
        add(manager, schedules=())


def test_as_needed_daily_limit(manager):
    add(manager, schedules=(), as_needed=True, max_doses_per_day=2)
    run(manager.async_log_dose("med_a", at(8, 0)))
    run(manager.async_log_dose("med_a", at(12, 0)))
    set_now(at(13, 0))
    with pytest.raises(Exception, match="limit"):
        run(manager.async_log_dose("med_a", at(13, 0)))
    row = manager.get_as_needed()[0]
    assert row["doses_today"] == 2 and row["at_limit"] is True
    # the next day it resets
    set_now(at(9, 0, 27))
    assert manager.get_as_needed()[0]["at_limit"] is False
    run(manager.async_log_dose("med_a", at(9, 0, 27)))


def test_as_needed_minimum_gap_uses_duplicate_guard(manager):
    add(manager, schedules=(), as_needed=True, duplicate_guard_minutes=240)
    run(manager.async_log_dose("med_a", at(8, 0)))
    set_now(at(9, 0))
    with pytest.raises(Exception, match="Duplicate"):
        run(manager.async_log_dose("med_a", at(9, 0)))


# ---------------------------------------------------------------- undo and who


def test_undo_last_removes_newest_and_restores_stock(manager):
    add(manager, quantity=10)
    run(manager.async_log_dose("med_a", at(7, 0), allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(8, 0), allow_duplicate=True))
    run(manager.async_undo_last("med_a"))
    logs = manager.medications["med_a"].dose_logs
    assert len(logs) == 1 and logs[0].taken_at == at(7, 0)
    assert manager.medications["med_a"].quantity == 9
    run(manager.async_undo_last("med_a"))
    with pytest.raises(Exception, match="no logged dose"):
        run(manager.async_undo_last("med_a"))


def test_undo_makes_dose_outstanding_again(manager):
    add(manager)
    prime(manager)
    set_now(at(8, 5))
    run(manager.async_log_dose("med_a", at(8, 5)))
    assert snap(manager)["outstanding"] is False
    run(manager.async_undo_last("med_a"))
    assert snap(manager)["outstanding"] is True


def test_taken_by_is_recorded_and_survives_restart(hass, manager):
    from mt.manager import MedicationTrackerManager

    add(manager)
    run(manager.async_log_dose("med_a", at(8, 0), allow_duplicate=True, taken_by="Sam"))
    run(manager.async_log_outstanding(source="x", taken_by="Alex"))  # nothing outstanding: no log
    assert snap(manager)["last_taken_by"] == "Sam"
    assert manager.get_recent_logs()[0]["taken_by"] == "Sam"
    fresh = MedicationTrackerManager(hass)
    run(fresh.async_initialize())
    assert fresh.medications["med_a"].dose_logs[0].taken_by == "Sam"


def test_take_all_records_who(manager):
    add(manager)
    prime(manager)
    set_now(at(8, 2))
    run(manager.async_log_outstanding(source="panel", taken_by="Mike"))
    assert manager.medications["med_a"].dose_logs[-1].taken_by == "Mike"


def test_backdated_dose_matches_the_right_slot(manager):
    add(manager, schedules=("08:00", "20:00"))
    for day in (24, 25):
        run(manager.async_log_dose("med_a", at(8, 0, day), allow_duplicate=True))
        run(manager.async_log_dose("med_a", at(20, 0, day), allow_duplicate=True))
    set_now(at(9, 30))
    run(manager.async_log_dose("med_a", at(8, 15)))  # tapped late, taken at 08:15
    s = snap(manager)
    assert s["outstanding"] is False and s["taken_today"] == 1 and s["missed_doses"] == 0


# ---------------------------------------------------------------- escalation


def escalating(manager, **kwargs):
    med = add(manager, escalate_after_minutes=30, caregiver_notify_service="notify.mobile_app_mum", **kwargs)
    prime(manager)
    return med


def test_escalation_fires_once_after_threshold(manager):
    escalating(manager)
    set_now(at(8, 20))
    assert [a for a in manager.get_pending_alerts() if a["type"] == "escalation"] == []
    set_now(at(8, 31))
    alerts = [a for a in manager.get_pending_alerts() if a["type"] == "escalation"]
    assert len(alerts) == 1
    assert alerts[0]["notify_service"] == "notify.mobile_app_mum"
    assert "has not taken Vitamin D" in alerts[0]["message"]
    assert [a["title"] for a in alerts[0]["actions"]] == ["Mark taken", "Skip"]
    run(manager.async_mark_alert_sent("med_a", "escalation", alerts[0]["scheduled_time"]))
    set_now(at(9, 0))
    assert [a for a in manager.get_pending_alerts() if a["type"] == "escalation"] == []


def test_no_escalation_when_taken_or_nobody_to_tell(manager):
    escalating(manager)
    set_now(at(8, 10))
    run(manager.async_log_dose("med_a", at(8, 10)))
    set_now(at(8, 45))
    assert [a for a in manager.get_pending_alerts() if a["type"] == "escalation"] == []
    add(manager, "med_b", "Other", escalate_after_minutes=30)  # no caregiver phone, no default
    prime(manager, "med_b")
    set_now(at(8, 45, 26))
    assert [a for a in manager.get_pending_alerts() if a["type"] == "escalation" and a["medication_id"] == "med_b"] == []


def test_escalation_falls_back_to_default_escalation_service(manager):
    add(manager, escalate_after_minutes=15)
    prime(manager)
    run(manager.async_update_settings({"escalation_notify_service": "notify.mobile_app_partner"}))
    set_now(at(8, 20))
    alerts = [a for a in manager.get_pending_alerts() if a["type"] == "escalation"]
    assert alerts and alerts[0]["notify_service"] == "notify.mobile_app_partner"


def test_escalation_delivery_event_and_clearing(hass, manager, engine):
    escalating(manager, notify_service="notify.mobile_app_me")
    set_now(at(8, 31))
    run(engine.async_process())
    mum = [c for c in hass.services.calls if c[0] == "notify.mobile_app_mum"]
    assert len(mum) == 1 and "has not taken" in mum[0][1]["message"]
    assert any(e[0] == EVENT_DOSE_ESCALATED for e in hass.bus.events)
    run(manager.async_log_dose("med_a", at(8, 32)))
    run(engine.async_dismiss_for_medications(["med_a"]))
    assert "medication_tracker_escalation_med_a" in hass.dismissed


# ---------------------------------------------------------------- notification style


def test_due_notification_is_alarm_style_by_default(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me")
    prime(manager)
    run(engine.async_process())
    data = [c for c in hass.services.calls if c[0] == "notify.mobile_app_me"][0][1]["data"]
    assert data["channel"] == "alarm_stream" and data["ttl"] == 0
    assert data["priority"] == "high" and data["importance"] == "high" and data["sticky"] == "true"


def test_alarm_style_can_be_turned_off_and_refill_never_uses_it(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me", quantity=1, refill_at=5)
    prime(manager)
    run(manager.async_update_settings({"critical_notifications": False}))
    run(engine.async_process())
    for call in [c for c in hass.services.calls if c[0] == "notify.mobile_app_me"]:
        assert "channel" not in call[1]["data"]
    run(manager.async_update_settings({"critical_notifications": True}))
    hass.services.calls.clear()
    set_now(at(8, 6))
    run(engine.async_process())  # repeat reminder
    refill = [c for c in hass.services.calls if "running low" in c[1]["message"]]
    due = [c for c in hass.services.calls if "due to take" in c[1]["message"]]
    assert all("channel" not in c[1]["data"] for c in refill)
    assert due and all(c[1]["data"]["channel"] == "alarm_stream" for c in due)


# ---------------------------------------------------------------- announcements


def announcements(hass):
    return [c for c in hass.services.calls if c[0] == "notify.alexa_media_kitchen"]


def test_announcement_spoken_for_due(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me")
    prime(manager)
    run(manager.async_update_settings({"announce_service": "notify.alexa_media_kitchen"}))
    run(engine.async_process())
    spoken = announcements(hass)
    assert len(spoken) == 1
    assert spoken[0][1]["message"] == "Medication reminder. Mike, please take Vitamin D."
    assert spoken[0][1]["data"] == {"type": "announce"}


def test_announcement_joins_several_names(hass, manager, engine):
    for ident, name in (("a", "Alpha"), ("b", "Beta"), ("c", "Gamma")):
        add(manager, ident, name, notify_service="notify.mobile_app_me")
        prime(manager, ident)
    run(manager.async_update_settings({"announce_service": "notify.alexa_media_kitchen"}))
    run(engine.async_process())
    assert announcements(hass)[0][1]["message"] == "Medication reminder. Mike, please take Alpha, Beta and Gamma."


def test_announcement_only_when_home(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me")
    prime(manager)
    run(
        manager.async_update_settings(
            {"announce_service": "notify.alexa_media_kitchen", "announce_only_when_home_entity": "person.mike"}
        )
    )
    hass.states.values["person.mike"] = "not_home"
    run(engine.async_process())
    assert announcements(hass) == []
    hass.states.values["person.mike"] = "home"
    set_now(at(8, 6))  # repeat reminder
    run(engine.async_process())
    assert len(announcements(hass)) == 1


def test_announcement_failure_is_harmless(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me")
    prime(manager)
    run(manager.async_update_settings({"announce_service": "notify.alexa_media_kitchen"}))
    hass.services.fail_with["notify.alexa_media_kitchen"] = ServiceNotFound("gone")
    run(engine.async_process())  # must not raise
    assert any(c[0] == "notify.mobile_app_me" for c in hass.services.calls)


# ---------------------------------------------------------------- quiet hours


def test_quiet_hours_defer_refill_and_silence_announcements(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_me", quantity=1, refill_at=5)
    prime(manager)
    run(
        manager.async_update_settings(
            {"quiet_hours_start": "07:00", "quiet_hours_end": "09:00", "announce_service": "notify.alexa_media_kitchen"}
        )
    )
    set_now(at(8, 0))
    alerts = manager.get_pending_alerts()
    assert not any(a["type"] == "refill" for a in alerts)
    assert any(a["type"] == "due" for a in alerts)  # dose reminders are never silenced
    run(engine.async_process())
    assert announcements(hass) == []
    set_now(at(9, 30))
    assert any(a["type"] == "refill" for a in manager.get_pending_alerts())


def test_quiet_hours_wrap_midnight(manager):
    run(manager.async_update_settings({"quiet_hours_start": "22:00", "quiet_hours_end": "07:00"}))
    assert manager._in_quiet_hours(at(23, 0)) and manager._in_quiet_hours(at(6, 59))
    assert not manager._in_quiet_hours(at(7, 0)) and not manager._in_quiet_hours(at(12, 0))


def test_bad_quiet_hours_rejected(manager):
    with pytest.raises(Exception):
        run(manager.async_update_settings({"quiet_hours_start": "late"}))


# ---------------------------------------------------------------- history limits


def test_old_logs_are_pruned_on_startup(hass, manager):
    from mt.manager import MedicationTrackerManager

    add(manager)
    old = at(8, 0) - timedelta(days=800)
    run(manager.async_log_dose("med_a", old, allow_duplicate=True))
    run(manager.async_log_dose("med_a", at(8, 0, 25), allow_duplicate=True))
    fresh = MedicationTrackerManager(hass)
    run(fresh.async_initialize())
    assert [log.taken_at for log in fresh.medications["med_a"].dose_logs] == [at(8, 0, 25)]


def test_matching_only_looks_back_a_year(manager):
    med = add(manager)
    med.start_date = date(2020, 1, 1)
    med.created_at = None
    state = manager._match_state(med, at(9, 0))
    assert len(state.occurrences) < 400


def test_old_data_without_new_fields_still_loads(hass):
    from mt.manager import MedicationTrackerManager

    hass.storage["medication_tracker"] = {
        "medications": [
            {
                "medication_id": "old", "profile_id": "mike", "profile_name": "Mike", "name": "Old",
                "dosage": "1", "schedules": ["08:00"], "start_date": "2026-01-01", "dose_logs": [],
            }
        ]
    }
    mgr = MedicationTrackerManager(hass)
    run(mgr.async_initialize())
    med = mgr.medications["old"]
    assert (med.interval_days, med.as_needed, med.end_date, med.escalate_after_minutes) == (1, False, None, 0)
    assert mgr.settings["critical_notifications"] is True
    assert mgr.get_snapshot("old")["course_ended"] is False
