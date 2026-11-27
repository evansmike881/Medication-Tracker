"""Tests for 0.6.0: pause mode, per-person phones, keep-apart and food notes, backup/restore,
daily backup files, weekly summary."""

import json
from types import SimpleNamespace

import pytest

from conftest import add, at, run, set_now


def prime(manager, ident="med_a", days=(24, 25), hour=8):
    for day in days:
        run(manager.async_log_dose(ident, at(hour, 0, day), allow_duplicate=True))


def due(manager):
    return [a for a in manager.get_pending_alerts() if a["type"] == "due"]


# ---------------------------------------------------------------- pause mode


def test_pause_stops_reminders_and_missed_counting(manager):
    add(manager)
    prime(manager)
    set_now(at(8, 0))
    assert len(due(manager)) == 1
    run(manager.async_add_pause(start="2026-11-26", end="2026-11-28"))
    assert due(manager) == []
    snap = manager.get_snapshot("med_a")
    assert snap["paused"] is True and snap["expected_doses_today"] == 0
    assert manager.get_today_doses() == []
    set_now(at(9, 30, 27))
    assert manager.get_snapshot("med_a")["missed_doses"] == 0


def test_paused_days_are_not_counted_missed_after_pause_ends(manager):
    add(manager)
    prime(manager)
    run(manager.async_add_pause(start="2026-11-26", end="2026-11-27"))
    prime(manager, days=(28, 29))  # taken on the two days after the pause
    set_now(at(12, 0, 29))  # the pause is over; 26th and 27th must not show as missed
    assert manager.get_snapshot("med_a")["paused"] is False
    assert manager.get_snapshot("med_a")["missed_doses"] == 0


def test_without_the_pause_those_days_would_be_missed(manager):
    add(manager)
    prime(manager)
    prime(manager, days=(28, 29))
    set_now(at(12, 0, 29))
    assert manager.get_snapshot("med_a")["missed_doses"] == 2


def test_pause_only_affects_chosen_person(manager):
    add(manager, "a", "A", profile="Mike")
    add(manager, "b", "B", profile="Sam")
    prime(manager, "a")
    prime(manager, "b")
    run(manager.async_add_pause(profile_id="mike", end="2026-11-30"))
    set_now(at(8, 0))
    ids = {d["medication_id"] for a in due(manager) for d in [{"medication_id": i} for i in a.get("medication_ids", [a["medication_id"]])]}
    assert ids == {"b"}


def test_pause_view_removal_and_validation(manager):
    add(manager)
    run(manager.async_add_pause(end="2026-12-01"))
    view = manager.get_pauses_view()
    assert len(view) == 1 and view[0]["active"] and view[0]["profile_name"] == "Everyone"
    run(manager.async_remove_pause(index=0))
    assert manager.get_pauses_view() == []
    with pytest.raises(Exception):
        run(manager.async_add_pause(start="2026-12-05", end="2026-12-01"))
    with pytest.raises(Exception):
        run(manager.async_add_pause(profile_id="nobody", end="2026-12-01"))
    with pytest.raises(Exception):
        run(manager.async_remove_pause(index=5))
    run(manager.async_add_pause(end="2026-12-01"))
    run(manager.async_remove_pause())  # resume everything that covers today
    assert manager.get_pauses_view() == []


def test_finished_pauses_are_hidden_but_future_ones_shown(manager):
    add(manager)
    run(manager.async_add_pause(start="2026-11-01", end="2026-11-05"))
    run(manager.async_add_pause(start="2026-12-20", end="2026-12-30"))
    view = manager.get_pauses_view()
    assert [v["start"] for v in view] == ["2026-12-20"] and view[0]["active"] is False


# ---------------------------------------------------------------- per-person phone


def test_person_phone_beats_default_but_not_medication_phone(manager):
    med = add(manager)
    run(manager.async_update_settings({"default_notify_service": "notify.default",
                                       "profile_notify_services": {"mike": "notify.mikes_phone"}}))
    assert manager.resolve_notify_service(med) == "notify.mikes_phone"
    med.notify_service = "notify.special"
    assert manager.resolve_notify_service(med) == "notify.special"
    other = add(manager, "b", "B", profile="Sam")
    assert manager.resolve_notify_service(other) == "notify.default"


def test_person_phone_is_used_by_engine(hass, manager, engine):
    add(manager)
    prime(manager)
    run(manager.async_update_settings({"profile_notify_services": {"mike": "notify.mikes_phone"}}))
    set_now(at(8, 0))
    run(engine.async_process())
    assert any(c[0] == "notify.mikes_phone" for c in hass.services.calls)


# ---------------------------------------------------------------- food notes and keep apart


def test_food_note_appears_in_reminder(manager):
    add(manager, food_note="with_food")
    prime(manager)
    set_now(at(8, 0))
    assert "take with food" in due(manager)[0]["message"]
    with pytest.raises(Exception):
        add(manager, food_note="whenever")


def test_conflict_when_scheduled_too_close(manager):
    add(manager, "iron", "Iron", schedules=("08:00",), keep_apart_minutes=120)
    add(manager, "calc", "Calcium", schedules=("09:00",), keep_apart=["iron"], keep_apart_minutes=120)
    conflicts = manager.get_snapshot("iron")["conflicts"]  # reverse side sees it too
    assert conflicts and conflicts[0]["medication_id"] == "calc" and conflicts[0]["gap_minutes"] == 60
    assert manager.get_snapshot("calc")["conflicts"][0]["required_minutes"] == 120


def test_no_conflict_when_far_enough_apart_or_unrelated(manager):
    add(manager, "iron", "Iron", schedules=("08:00",))
    add(manager, "calc", "Calcium", schedules=("12:00",), keep_apart=["iron"], keep_apart_minutes=120)
    add(manager, "zinc", "Zinc", schedules=("08:05",))
    assert manager.get_snapshot("calc")["conflicts"] == []
    assert manager.get_snapshot("zinc")["conflicts"] == []


def test_keep_apart_across_midnight(manager):
    add(manager, "a", "A", schedules=("23:30",))
    add(manager, "b", "B", schedules=("00:30",), keep_apart=["a"], keep_apart_minutes=120)
    assert manager.get_snapshot("b")["conflicts"][0]["gap_minutes"] == 60


def test_keep_apart_warning_after_dose(manager):
    add(manager, "iron", "Iron", schedules=("08:00",))
    add(manager, "calc", "Calcium", schedules=("12:00",), keep_apart=["iron"], keep_apart_minutes=120)
    run(manager.async_log_dose("iron", at(7, 40)))
    set_now(at(8, 0))
    assert "Iron was taken 20 minutes ago" in manager.keep_apart_warnings("calc")[0]
    set_now(at(10, 30))
    assert manager.keep_apart_warnings("calc") == []


def test_keep_apart_validation_and_self_reference(manager):
    add(manager, "iron", "Iron")
    with pytest.raises(Exception):
        add(manager, "calc", "Calcium", keep_apart=["ghost"])
    med = add(manager, "calc", "Calcium", keep_apart=["calc", "iron"])
    assert med.keep_apart == ["iron"]


def test_editing_without_new_fields_keeps_them(manager):
    add(manager, food_note="empty_stomach", keep_apart_minutes=90)
    med = add(manager)  # saved again without mentioning the new fields
    assert med.food_note == "empty_stomach" and med.keep_apart_minutes == 90


# ---------------------------------------------------------------- backup and restore


def test_export_import_round_trip(hass, manager, tmp_path):
    hass.config = SimpleNamespace(path=lambda *p: str(tmp_path.joinpath(*p)))
    add(manager, "a", "A", schedules=("20:00",))
    add(manager, "b", "B", schedules=("20:00",))
    run(manager.async_save_group(profile_id="mike", profile_name="Mike", name="Evening",
                                 schedules=["20:00"], member_ids=["a", "b"], nfc_tag_id="tag1"))
    prime(manager, "a", hour=20)
    run(manager.async_update_settings({"default_notify_service": "notify.x"}))
    backup = json.loads(json.dumps(manager.export_data()))  # must survive JSON

    for ident in list(manager.medications):
        run(manager.async_remove_medication(ident))
    manager.groups.clear()
    run(manager.async_update_settings({"default_notify_service": None}))
    assert not manager.medications

    result = run(manager.async_import_data(backup))
    assert result == {"medications": 2, "groups": 1}
    assert len(manager.medications["a"].dose_logs) == 2
    assert manager.medications["a"].group_id == manager.medications["b"].group_id
    assert manager.groups[manager.medications["a"].group_id].nfc_tag_id == "tag1"
    assert manager.settings["default_notify_service"] == "notify.x"


def test_import_keeps_a_safety_copy_of_what_it_replaces(hass, manager, tmp_path):
    hass.config = SimpleNamespace(path=lambda *p: str(tmp_path.joinpath(*p)))
    add(manager)
    backup = manager.export_data()
    add(manager, "extra", "Extra")
    run(manager.async_import_data(backup))
    saved = json.loads((tmp_path / "medication_tracker_backups" / "medication_tracker_before_restore.json").read_text())
    assert {m["medication_id"] for m in saved["medications"]} == {"med_a", "extra"}
    assert set(manager.medications) == {"med_a"}


def test_import_rejects_bad_files_and_leaves_data_alone(manager):
    add(manager)
    for bad in (None, [], {"format": "something else"}, {"format": "medication_tracker_backup", "medications": [{"x": 1}]}):
        with pytest.raises(Exception):
            run(manager.async_import_data(bad))
    assert "med_a" in manager.medications


def test_import_clears_dangling_group_references(manager):
    add(manager)
    backup = manager.export_data()
    backup["medications"][0]["group_id"] = "gone"
    run(manager.async_import_data(backup))
    assert manager.medications["med_a"].group_id is None


def test_daily_backup_file_once_per_day_and_pruned(hass, manager, tmp_path):
    hass.config = SimpleNamespace(path=lambda *p: str(tmp_path.joinpath(*p)))
    folder = tmp_path / "medication_tracker_backups"
    folder.mkdir()
    for day in range(1, 21):
        (folder / f"medication_tracker_2026-10-{day:02d}.json").write_text("{}")
    add(manager)
    run(manager.async_auto_backup())
    files = sorted(p.name for p in folder.glob("medication_tracker_20*.json"))
    assert len(files) == 14 and files[-1] == "medication_tracker_2026-11-26.json"
    (folder / "medication_tracker_2026-11-26.json").unlink()
    run(manager.async_auto_backup())  # same day: not rewritten
    assert not (folder / "medication_tracker_2026-11-26.json").exists()
    set_now(at(8, 0, 27))
    run(manager.async_auto_backup())
    assert (folder / "medication_tracker_2026-11-27.json").exists()


def test_backup_failure_never_raises_and_empty_installs_skip(hass, manager):
    run(manager.async_auto_backup())  # nothing to back up yet
    add(manager)
    set_now(at(8, 0, 27))
    run(manager.async_auto_backup())  # FakeHass has no config: must be swallowed


# ---------------------------------------------------------------- weekly summary


def test_weekly_summary_counts_and_lists_misses(manager):
    add(manager)
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))  # Tue taken, Wed missed
    set_now(at(10, 0))
    summary = manager.get_weekly_summary()
    person = summary["people"][0]
    assert (person["taken"], person["expected"]) == (1, 2)
    assert "Mike: 1 of 2 doses taken (50%)" in summary["message"]
    assert "Vitamin D (Wed)" in summary["message"]


def test_weekly_summary_ignores_skipped_paused_and_as_needed(manager):
    add(manager)
    add(manager, "prn", "Paracetamol", as_needed=True, schedules=())
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))
    run(manager.async_skip_medication_occurrence("med_a", at(8, 0, 25)))
    set_now(at(10, 0))
    person = manager.get_weekly_summary()["people"][0]
    assert (person["taken"], person["expected"], person["skipped"]) == (1, 1, 1)


def test_weekly_summary_mentions_low_stock(manager):
    add(manager, quantity=3, refill_at=5)
    set_now(at(10, 0))
    assert "Running low: Vitamin D" in manager.get_weekly_summary()["message"]


def test_weekly_summary_due_rules(manager):
    set_now(at(10, 0))  # a Thursday
    assert manager.weekly_summary_due() is False  # no phone chosen
    run(manager.async_update_settings({"weekly_summary_service": "notify.x", "weekly_summary_day": 3}))
    assert manager.weekly_summary_due() is True
    set_now(at(8, 59))
    assert manager.weekly_summary_due() is False  # too early
    set_now(at(10, 0))
    run(manager.async_mark_weekly_sent(at(10, 0).date()))
    assert manager.weekly_summary_due() is False  # already sent today
    run(manager.async_update_settings({"weekly_summary_day": 5}))
    assert manager.weekly_summary_due() is False  # wrong day
    with pytest.raises(Exception):
        run(manager.async_update_settings({"weekly_summary_day": 9}))


def test_engine_sends_weekly_summary_once(hass, manager, engine):
    add(manager)
    run(manager.async_log_dose("med_a", at(8, 0, 24), allow_duplicate=True))
    run(manager.async_update_settings({"weekly_summary_service": "notify.mobile_app_mike", "weekly_summary_day": 3}))
    set_now(at(10, 0))
    run(engine.async_process())
    sent = [c for c in hass.services.calls if c[0] == "notify.mobile_app_mike" and "Last week" in c[1]["message"]]
    assert len(sent) == 1
    assert "actions" in sent[0][1]["data"] and sent[0][1]["data"]["actions"] == []
    set_now(at(10, 5))
    run(engine.async_process())
    assert len([c for c in hass.services.calls if c[0] == "notify.mobile_app_mike" and "Last week" in c[1]["message"]]) == 1


def test_refill_message_includes_days_left(manager):
    add(manager, quantity=3, refill_at=5)
    set_now(at(10, 0))
    refill = [a for a in manager.get_pending_alerts() if a["type"] == "refill"][0]
    assert "about 3 days left" in refill["message"]
