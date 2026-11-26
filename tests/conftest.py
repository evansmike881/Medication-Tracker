"""Test harness.

Home Assistant is not installed in CI for this repo, so the pieces of Home Assistant that
the business logic touches are replaced with small fakes. The tests exercise the real
manager, alert engine, store and models. They do NOT exercise code that needs a running
Home Assistant (config flow, platforms, panel registration, websocket wiring).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import sys
import types
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

PKG_DIR = Path(__file__).resolve().parents[1] / "custom_components" / "medication_tracker"
TZ = ZoneInfo("Europe/London")


class HomeAssistantError(Exception):
    pass


class ServiceNotFound(HomeAssistantError):
    pass


class _Clock:
    current = datetime(2026, 11, 26, 8, 0, tzinfo=TZ)


def _module(name: str, **attrs):
    mod = types.ModuleType(name)
    mod.__dict__.update(attrs)
    sys.modules[name] = mod
    return mod


class FakeServices:
    def __init__(self):
        self.calls = []
        self.fail_with = {}

    async def async_call(self, domain, service, data=None, blocking=False):
        self.calls.append((f"{domain}.{service}", data, blocking))
        exc = self.fail_with.get(f"{domain}.{service}")
        if exc:
            raise exc


class FakeBus:
    def __init__(self):
        self.events = []

    def async_fire(self, event_type, data=None):
        self.events.append((event_type, data))


class _FakeState:
    def __init__(self, state):
        self.state = state


class FakeStates:
    def __init__(self):
        self.values = {}

    def get(self, entity_id):
        value = self.values.get(entity_id)
        return _FakeState(value) if value is not None else None


class FakeHass:
    def __init__(self):
        self.states = FakeStates()
        self.data = {}
        self.services = FakeServices()
        self.bus = FakeBus()
        self.storage = {}
        self.notifications = {}
        self.dismissed = []
        self.issues = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class FakeStore:
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, version, key):
        self._hass, self._key = hass, key

    async def async_load(self):
        import copy

        return copy.deepcopy(self._hass.storage.get(self._key))

    async def async_save(self, data):
        import copy

        self._hass.storage[self._key] = copy.deepcopy(data)


def _install_stubs():
    _module("homeassistant")
    _module("homeassistant.core", HomeAssistant=FakeHass, callback=lambda f: f)
    _module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError, ServiceNotFound=ServiceNotFound)

    def slugify(text):
        import re

        return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_")

    dt = _module(
        "homeassistant.util.dt",
        DEFAULT_TIME_ZONE=TZ,
        now=lambda: _Clock.current,
        as_local=lambda value: value.astimezone(TZ) if value.tzinfo else value.replace(tzinfo=TZ),
        as_utc=lambda value: value,
    )
    _module("homeassistant.util", slugify=slugify, dt=dt)
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.storage", Store=FakeStore)

    sent = []
    _module("homeassistant.helpers.dispatcher", async_dispatcher_send=lambda hass, signal, *a: sent.append(signal))

    class IssueSeverity:
        WARNING = "warning"

    def create_issue(hass, domain, issue_id, **kwargs):
        hass.issues[issue_id] = kwargs

    def delete_issue(hass, domain, issue_id):
        hass.issues.pop(issue_id, None)

    ir = _module(
        "homeassistant.helpers.issue_registry",
        IssueSeverity=IssueSeverity,
        async_create_issue=create_issue,
        async_delete_issue=delete_issue,
    )
    sys.modules["homeassistant.helpers"].issue_registry = ir

    def pn_create(hass, message, title=None, notification_id=None):
        hass.notifications[notification_id] = message

    def pn_dismiss(hass, notification_id):
        hass.dismissed.append(notification_id)
        hass.notifications.pop(notification_id, None)

    pn = _module("homeassistant.components.persistent_notification", async_create=pn_create, async_dismiss=pn_dismiss)
    _module("homeassistant.components", persistent_notification=pn)


_install_stubs()

# Load the integration's modules under an alias so its __init__ (which needs a real
# Home Assistant) is never executed.
_pkg = types.ModuleType("mt")
_pkg.__path__ = [str(PKG_DIR)]
sys.modules["mt"] = _pkg


def set_now(value: datetime) -> None:
    _Clock.current = value


def at(hour: int, minute: int = 0, day: int = 26) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TZ)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hass():
    set_now(at(8, 0))
    return FakeHass()


@pytest.fixture
def manager(hass):
    from mt.manager import MedicationTrackerManager

    mgr = MedicationTrackerManager(hass)
    run(mgr.async_initialize())
    return mgr


@pytest.fixture
def engine(hass, manager):
    from mt.alerts import MedicationAlertEngine

    return MedicationAlertEngine(hass, manager)


def add(manager, medication_id="med_a", name="Vitamin D", profile="Mike", schedules=("08:00",), **kwargs):
    """Add a medication as if it had been created at the start of 2026-11-24."""
    params = dict(
        profile_id=profile.lower(),
        profile_name=profile,
        medication_id=medication_id,
        medication_name=name,
        dosage="1 tablet",
        schedules=list(schedules),
    )
    params.update(kwargs)
    medication = run(manager.async_add_medication(**params))
    from datetime import date

    medication.start_date = date(2026, 11, 24)
    medication.created_at = at(0, 0, 24).isoformat()
    return medication
