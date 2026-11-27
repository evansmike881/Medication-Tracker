"""Tests for 0.5.0: groups, quick add, drag-and-drop ordering, group notifications and tags."""

import pytest

from conftest import add, at, run, set_now


def make_group(manager, ids=("vd", "mg", "zn"), name="Morning vitamins", **kwargs):
    for ident in ids:
        if ident not in manager.medications:
            add(manager, ident, ident.upper(), schedules=("20:00",))
    params = dict(
        profile_id="mike",
        profile_name="Mike",
        name=name,
        schedules=["08:00"],
        member_ids=list(ids),
    )
    params.update(kwargs)
    return run(manager.async_save_group(**params))


def prime(manager, ids, days=(24, 25)):
    for ident in ids:
        for day in days:
            run(manager.async_log_dose(ident, at(8, 0, day), allow_duplicate=True))


def due(manager):
    return [a for a in manager.get_pending_alerts() if a["type"] == "due"]


# ---------------------------------------------------------------- membership and schedule


def test_group_pushes_its_schedule_onto_members(manager):
    group = make_group(manager, days_of_week=[0, 2], interval_days=1)
    for ident in ("vd", "mg", "zn"):
        med = manager.medications[ident]
        assert med.group_id == group.group_id
        assert med.schedules == ["08:00"]
        assert med.days_of_week == [0, 2]


def test_editing_group_times_moves_every_member(manager):
    group = make_group(manager)
    run(manager.async_save_group(group_id=group.group_id, profile_id="mike", profile_name="Mike",
                                 name="Morning vitamins", schedules=["09:30", "21:00"]))
    for ident in ("vd", "mg", "zn"):
        assert manager.medications[ident].schedules == ["09:30", "21:00"]


def test_member_list_replaced_and_dropped_members_keep_schedule(manager):
    group = make_group(manager)
    run(manager.async_save_group(group_id=group.group_id, profile_id="mike", profile_name="Mike",
                                 name="Morning vitamins", schedules=["08:00"], member_ids=["zn", "vd"]))
    assert [m.medication_id for m in manager.group_members(group.group_id)] == ["zn", "vd"]
    assert manager.medications["mg"].group_id is None
    assert manager.medications["mg"].schedules == ["08:00"]


def test_group_rules_enforced(manager):
    add(manager, "other", "Other", profile="Sam")
    add(manager, "prn", "Paracetamol", as_needed=True, schedules=())
    with pytest.raises(Exception):
        make_group(manager, ids=("other",))  # belongs to Sam, group is Mike's
    with pytest.raises(Exception):
        make_group(manager, ids=("prn",))  # as-needed cannot be timed
    with pytest.raises(Exception):
        make_group(manager, ids=(), name="  ")
    with pytest.raises(Exception):
        make_group(manager, ids=(), name="Bad", schedules=["99:99"])


def test_deleting_group_keeps_medications(manager):
    group = make_group(manager)
    run(manager.async_delete_group(group.group_id))
    assert group.group_id not in manager.groups
    for ident in ("vd", "mg", "zn"):
        assert manager.medications[ident].group_id is None
        assert manager.medications[ident].schedules == ["08:00"]


def test_groups_survive_restart(hass, manager):
    group = make_group(manager)
    from mt.manager import MedicationTrackerManager

    fresh = MedicationTrackerManager(hass)
    run(fresh.async_initialize())
    assert group.group_id in fresh.groups
    assert fresh.medications["vd"].group_id == group.group_id
    assert [g["member_ids"] for g in fresh.get_groups_view()] == [["vd", "mg", "zn"]]


def test_deleting_medication_removes_it_from_group_view(manager):
    group = make_group(manager)
    run(manager.async_remove_medication("mg"))
    assert manager.get_groups_view()[0]["member_ids"] == ["vd", "zn"]
    assert group.group_id in manager.groups


# ---------------------------------------------------------------- drag and drop


def test_move_medication_into_group_at_position(manager):
    group = make_group(manager, ids=("vd", "mg"))
    add(manager, "bp", "Blood pressure", schedules=("09:00",))
    run(manager.async_move_medication("bp", group.group_id, 1))
    assert [m.medication_id for m in manager.group_members(group.group_id)] == ["vd", "bp", "mg"]
    assert manager.medications["bp"].schedules == ["08:00"]  # took the group's time


def test_move_out_of_group_and_reorder_within(manager):
    group = make_group(manager)
    run(manager.async_move_medication("vd", None))
    assert manager.medications["vd"].group_id is None
    assert [m.medication_id for m in manager.group_members(group.group_id)] == ["mg", "zn"]
    run(manager.async_move_medication("zn", group.group_id, 0))
    assert [m.medication_id for m in manager.group_members(group.group_id)] == ["zn", "mg"]


def test_move_validations(manager):
    group = make_group(manager, ids=("vd",))
    add(manager, "other", "Other", profile="Sam")
    add(manager, "prn", "Paracetamol", as_needed=True, schedules=())
    with pytest.raises(Exception):
        run(manager.async_move_medication("other", group.group_id, 0))
    with pytest.raises(Exception):
        run(manager.async_move_medication("prn", group.group_id, 0))
    with pytest.raises(Exception):
        run(manager.async_move_medication("vd", "nope", 0))


def test_reorder_groups(manager):
    a = make_group(manager, ids=("vd",), name="A")
    b = make_group(manager, ids=("mg",), name="B", schedules=["12:00"])
    c = make_group(manager, ids=("zn",), name="C", schedules=["20:00"])
    run(manager.async_reorder_groups("mike", [c.group_id, a.group_id]))
    assert [g["group_id"] for g in manager.get_groups_view()] == [c.group_id, a.group_id, b.group_id]
    with pytest.raises(Exception):
        run(manager.async_reorder_groups("mike", ["nope"]))


def test_today_view_is_ordered_by_time_then_group_then_position(manager):
    g1 = make_group(manager, ids=("vd", "mg"), name="Vitamins")
    add(manager, "bp", "BP", schedules=("08:00",))
    run(manager.async_move_medication("mg", g1.group_id, 0))
    set_now(at(7, 0))
    names = [(d["medication_id"], d["group_name"]) for d in manager.get_today_doses()]
    assert names[:2] == [("mg", "Vitamins"), ("vd", "Vitamins")]
    assert names[2][0] == "bp"  # ungrouped sorts after groups


# ---------------------------------------------------------------- quick add


def test_quick_add_into_new_group(manager):
    result = run(manager.async_quick_add(
        profile_name="Mike",
        items=[{"name": "Vitamin C", "dosage": "500 mg"}, {"name": "Zinc"}, {"name": "  "}],
        new_group={"name": "Morning vitamins", "schedules": ["08:00"]},
    ))
    assert len(result["created"]) == 2
    group = manager.groups[result["group_id"]]
    assert [m.name for m in manager.group_members(group.group_id)] == ["Vitamin C", "Zinc"]
    assert manager.medications[result["created"][0]].dosage == "500 mg"
    assert manager.medications[result["created"][1]].dosage == "1 dose"


def test_quick_add_into_existing_group_and_ungrouped(manager):
    group = make_group(manager, ids=("vd",))
    run(manager.async_quick_add(profile_name="Mike", items=[{"name": "Iodine"}], group_id=group.group_id))
    assert len(manager.group_members(group.group_id)) == 2
    result = run(manager.async_quick_add(profile_name="Mike", items=[{"name": "Aspirin"}], schedules=["10:00"]))
    med = manager.medications[result["created"][0]]
    assert med.group_id is None and med.schedules == ["10:00"]


def test_quick_add_needs_somewhere_to_go_and_something_to_add(manager):
    with pytest.raises(Exception):
        run(manager.async_quick_add(profile_name="Mike", items=[{"name": "X"}]))
    with pytest.raises(Exception):
        run(manager.async_quick_add(profile_name="Mike", items=[], schedules=["08:00"]))
    with pytest.raises(Exception):
        run(manager.async_quick_add(profile_name="", items=[{"name": "X"}], schedules=["08:00"]))


def test_quick_add_duplicate_names_get_unique_ids(manager):
    run(manager.async_quick_add(profile_name="Mike", items=[{"name": "Zinc"}, {"name": "Zinc"}], schedules=["08:00"]))
    assert len(manager.medications) == 2


# ---------------------------------------------------------------- notifications


def test_group_is_one_notification_with_group_title_and_actions(manager):
    group = make_group(manager)
    prime(manager, ("vd", "mg", "zn"))
    set_now(at(8, 0))
    alerts = due(manager)
    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["title"] == "Morning vitamins"
    assert [a["action"] for a in alert["actions"]] == [
        f"MEDICATION_GROUP_{group.group_id}",
        f"MEDICATION_GROUPSNOOZE_{group.group_id}",
    ]
    for name in ("VD", "MG", "ZN"):
        assert name in alert["message"]


def test_group_plus_separate_medication_sections_the_message(manager):
    make_group(manager, ids=("vd", "mg"))
    add(manager, "bp", "Blood pressure", schedules=("08:00",))
    prime(manager, ("vd", "mg", "bp"))
    set_now(at(8, 0))
    alerts = due(manager)
    assert len(alerts) == 1
    assert "Morning vitamins" in alerts[0]["message"] and "Blood pressure" in alerts[0]["message"]
    assert alerts[0]["actions"][0]["action"].startswith("MEDICATION_ALL_")


def test_groups_for_different_people_do_not_merge(manager):
    make_group(manager, ids=("vd",), name="Mike AM")
    add(manager, "sam1", "Sam vit", profile="Sam", schedules=("20:00",))
    run(manager.async_save_group(profile_id="sam", profile_name="Sam", name="Sam AM", schedules=["08:00"], member_ids=["sam1"]))
    prime(manager, ("vd", "sam1"))
    set_now(at(8, 0))
    assert len(due(manager)) == 2


def test_group_notifications_can_be_switched_off(manager):
    make_group(manager, notification_enabled=False)
    prime(manager, ("vd", "mg", "zn"))
    set_now(at(8, 0))
    assert due(manager) == []


def test_group_notify_service_override_reaches_members(hass, manager, engine):
    make_group(manager, notify_service="notify.mobile_app_mike_s24")
    prime(manager, ("vd", "mg", "zn"))
    set_now(at(8, 0))
    run(engine.async_process())
    calls = [c for c in hass.services.calls if c[0] == "notify.mobile_app_mike_s24"]
    assert len(calls) == 1
    assert calls[0][1]["title"] == "Morning vitamins"


# ---------------------------------------------------------------- taking


def test_take_group_logs_each_member_individually(manager):
    group = make_group(manager)
    add(manager, "bp", "BP", schedules=("08:00",))
    prime(manager, ("vd", "mg", "zn", "bp"))
    set_now(at(8, 0))
    result = run(manager.async_log_outstanding(group_id=group.group_id, source="notification"))
    assert sorted(result["logged"]) == ["mg", "vd", "zn"]
    for ident in ("vd", "mg", "zn"):
        assert manager.medications[ident].dose_logs[-1].taken_at.day == 26
    assert manager.medications["bp"].dose_logs[-1].taken_at.day == 25  # untouched


def test_take_selected_ids_only(manager):
    make_group(manager)
    prime(manager, ("vd", "mg", "zn"))
    set_now(at(8, 0))
    result = run(manager.async_log_outstanding(medication_ids=["mg", "zn"]))
    assert sorted(result["logged"]) == ["mg", "zn"]
    assert manager.outstanding_ids() == ["vd"]


def test_individual_tick_leaves_group_partly_done(manager):
    group = make_group(manager)
    prime(manager, ("vd", "mg", "zn"))
    set_now(at(8, 0))
    run(manager.async_log_dose("mg", at(8, 1)))
    assert sorted(manager.outstanding_ids(group_id=group.group_id)) == ["vd", "zn"]
    alert = due(manager)[0]
    assert "MG" not in alert["message"]  # only what is left is shown


def test_each_member_missed_individually(manager):
    make_group(manager)
    prime(manager, ("vd", "mg", "zn"))
    run(manager.async_log_dose("vd", at(8, 0), allow_duplicate=True))
    set_now(at(8, 0, 27))  # a full day later, mg and zn never taken on the 26th
    assert manager.get_snapshot("mg")["missed_doses"] == 1
    assert manager.get_snapshot("vd")["missed_doses"] == 0


# ---------------------------------------------------------------- nfc


def test_group_nfc_tag_resolves_to_group(manager):
    group = make_group(manager, nfc_tag_id="tag-group")
    kind, found = manager.resolve_tag("tag-group")
    assert kind == "group" and found.group_id == group.group_id
    assert manager.resolve_tag("unknown") is None


# ---------------------------------------------------------------- medication form path


def test_add_medication_with_group_id_uses_group_schedule(manager):
    group = make_group(manager, ids=("vd",))
    med = run(manager.async_add_medication(
        profile_id="mike", profile_name="Mike", medication_id="new", medication_name="New",
        dosage="1", schedules=[], group_id=group.group_id))
    assert med.group_id == group.group_id and med.schedules == ["08:00"]


def test_editing_member_without_group_id_keeps_group(manager):
    group = make_group(manager, ids=("vd",))
    med = run(manager.async_add_medication(
        profile_id="mike", profile_name="Mike", medication_id="vd", medication_name="VD2",
        dosage="2", schedules=["20:00"]))
    assert med.group_id == group.group_id and med.schedules == ["08:00"]


def test_empty_string_group_id_clears_group(manager):
    make_group(manager, ids=("vd",))
    med = run(manager.async_add_medication(
        profile_id="mike", profile_name="Mike", medication_id="vd", medication_name="VD",
        dosage="1", schedules=["20:00"], group_id=""))
    assert med.group_id is None and med.schedules == ["20:00"]


def test_as_needed_is_never_grouped(manager):
    group = make_group(manager, ids=("vd",))
    med = run(manager.async_add_medication(
        profile_id="mike", profile_name="Mike", medication_id="p", medication_name="P",
        dosage="1", schedules=[], as_needed=True, group_id=group.group_id))
    assert med.group_id is None and med.as_needed


def test_outstanding_ids_filters_by_group(manager):
    group = make_group(manager)
    add(manager, "bp", "BP", schedules=("08:00",))
    prime(manager, ("vd", "mg", "zn", "bp"))
    set_now(at(8, 0))
    assert sorted(manager.outstanding_ids()) == ["bp", "mg", "vd", "zn"]
    assert sorted(manager.outstanding_ids(group_id=group.group_id)) == ["mg", "vd", "zn"]
