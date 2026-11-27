# Tests

    python -m pytest tests

These run the real manager, alert engine, store and models against small fakes of the Home
Assistant pieces they touch (see `conftest.py`). Home Assistant itself is not required.

They do **not** cover code that needs a running Home Assistant: the config flow, entity
platforms, panel/static-path registration, websocket wiring and the `tag_scanned` /
`mobile_app_notification_action` listeners. Verify those on a real instance after install.

CI (`.github/workflows`) runs these on every push, plus Home Assistant's hassfest and the
HACS validator. The two validators are set to non-blocking until they have been seen passing.
