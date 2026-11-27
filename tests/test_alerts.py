"""Tests for the alert engine: delivery, failures, clearing."""

from mt.const import EVENT_DOSE_DUE

from conftest import ServiceNotFound, add, at, run, set_now


def due_med(manager, ident="med_a", name="Vitamin D", **kwargs):
    med = add(manager, ident, name, **kwargs)
    for day in (24, 25):
        run(manager.async_log_dose(ident, at(8, 0, day), allow_duplicate=True))
    return med


def test_notification_is_sent_with_actions_and_tag(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_mike_s24")
    run(engine.async_process())
    call = [c for c in hass.services.calls if c[0] == "notify.mobile_app_mike_s24"][0]
    data = call[1]
    assert "Vitamin D" in data["message"]
    assert data["data"]["tag"] == "medication_tracker_due_med_a"
    assert [a["title"] for a in data["data"]["actions"]] == ["Taken", "Snooze 10 min", "Skip"]
    assert any(e[0] == EVENT_DOSE_DUE for e in hass.bus.events)


def test_default_notify_service_is_used(hass, manager, engine):
    due_med(manager)
    run(manager.async_update_settings({"default_notify_service": "notify.mobile_app_default"}))
    run(engine.async_process())
    assert any(c[0] == "notify.mobile_app_default" for c in hass.services.calls)


def test_failed_delivery_is_retried_until_the_phone_comes_back(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_gone")
    hass.services.fail_with["notify.mobile_app_gone"] = ServiceNotFound("nope")

    run(engine.async_process())  # must not raise
    assert "notify_target_missing_notify_mobile_app_gone" in hass.issues  # visible in Repairs
    due_events = lambda: [e for e in hass.bus.events if e[0] == EVENT_DOSE_DUE]
    assert len(due_events()) == 1

    set_now(at(8, 1))
    run(engine.async_process())
    set_now(at(8, 2))
    run(engine.async_process())
    sends = [c for c in hass.services.calls if c[0] == "notify.mobile_app_gone"]
    assert len(sends) == 3  # retried every minute
    assert len(due_events()) == 1  # but the event and popup are not repeated

    del hass.services.fail_with["notify.mobile_app_gone"]  # phone re-registered
    set_now(at(8, 3))
    run(engine.async_process())
    assert len([c for c in hass.services.calls if c[0] == "notify.mobile_app_gone"]) == 4
    assert "notify_target_missing_notify_mobile_app_gone" not in hass.issues

    set_now(at(8, 4))
    run(engine.async_process())  # delivered, so it is now marked sent and stops
    assert len([c for c in hass.services.calls if c[0] == "notify.mobile_app_gone"]) == 4


def test_delivery_retries_stop_after_the_limit(hass, manager, engine, monkeypatch):
    from mt import alerts

    monkeypatch.setattr(alerts, "MAX_DELIVERY_ATTEMPTS", 5)

    due_med(manager, notify_service="notify.mobile_app_gone", repeat_every_minutes=0)
    hass.services.fail_with["notify.mobile_app_gone"] = ServiceNotFound("nope")
    for minute in range(10):
        set_now(at(8, 0) + __import__("datetime").timedelta(minutes=minute))
        run(engine.async_process())
    sends = [c for c in hass.services.calls if c[0] == "notify.mobile_app_gone" and "due" in c[1]["message"]]
    assert len(sends) == alerts.MAX_DELIVERY_ATTEMPTS


def test_fallback_service_used_when_primary_fails(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_gone")
    run(manager.async_update_settings({"fallback_notify_service": "notify.mobile_app_backup"}))
    hass.services.fail_with["notify.mobile_app_gone"] = ServiceNotFound("nope")
    run(engine.async_process())
    assert any(c[0] == "notify.mobile_app_backup" for c in hass.services.calls)


def test_issue_cleared_when_service_recovers(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_x", repeat_every_minutes=5)
    hass.services.fail_with["notify.mobile_app_x"] = ServiceNotFound("nope")
    run(engine.async_process())
    assert hass.issues
    hass.services.fail_with.clear()
    set_now(at(8, 5))  # repeat reminder goes out
    run(engine.async_process())
    assert not hass.issues


def test_notification_stays_until_dose_taken_then_clears_phone_too(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_mike_s24")
    run(engine.async_process())
    set_now(at(8, 2))
    run(engine.async_process())
    assert hass.dismissed == []  # old code dismissed it a minute after sending
    assert "medication_tracker_due_med_a" in hass.notifications

    run(manager.async_log_dose("med_a", at(8, 3), allow_duplicate=True))
    run(engine.async_dismiss_for_medications(["med_a"]))
    assert "medication_tracker_due_med_a" in hass.dismissed
    clear = [c for c in hass.services.calls if c[1].get("message") == "clear_notification"]
    assert clear and clear[0][1]["data"]["tag"] == "medication_tracker_due_med_a"


def test_clears_when_window_passes_without_dose(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_mike_s24")
    run(engine.async_process())
    set_now(at(8, 20))  # reminder window is 15 minutes
    run(engine.async_process())
    assert "medication_tracker_due_med_a" in hass.dismissed


def test_group_notification_stays_if_one_medication_remains(hass, manager, engine):
    due_med(manager, "med_a", "A", notify_service="notify.mobile_app_p")
    due_med(manager, "med_b", "B", notify_service="notify.mobile_app_p")
    run(engine.async_process())
    group_id = [n for n in hass.notifications if "med_a_med_b" in n][0]
    run(manager.async_log_dose("med_a", at(8, 1), allow_duplicate=True))
    run(engine.async_dismiss_for_medications(["med_a"]))
    assert group_id not in hass.dismissed
    run(manager.async_log_dose("med_b", at(8, 2), allow_duplicate=True))
    run(engine.async_dismiss_for_medications(["med_b"]))
    assert group_id in hass.dismissed


def test_test_notification_reports_failure(hass, manager, engine):
    add(manager, notify_service="notify.mobile_app_gone")
    hass.services.fail_with["notify.mobile_app_gone"] = ServiceNotFound("nope")
    assert run(engine.async_send_test_alert("med_a", "due")) is False
    hass.services.fail_with.clear()
    assert run(engine.async_send_test_alert("med_a", "due")) is True


def test_invalid_service_name_is_reported_not_raised(hass, manager, engine):
    due_med(manager, notify_service="mobile_app_without_domain")
    run(engine.async_process())
    assert any(i.startswith("notify_target_missing_") for i in hass.issues)


def test_unexpected_error_in_one_alert_still_marks_it_sent(hass, manager, engine):
    due_med(manager, notify_service="notify.mobile_app_mike_s24")

    def boom(*args, **kwargs):
        raise RuntimeError("bus exploded")

    hass.bus.async_fire = boom
    run(engine.async_process())  # must not raise
    assert manager.medications["med_a"].last_due_notification is not None
    sends_before = len([c for c in hass.services.calls if c[0] == "notify.mobile_app_mike_s24"])
    set_now(at(8, 1))
    run(engine.async_process())
    sends_after = len([c for c in hass.services.calls if c[0] == "notify.mobile_app_mike_s24"])
    assert sends_after == sends_before  # no retry storm
