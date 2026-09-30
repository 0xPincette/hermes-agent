from types import SimpleNamespace
import threading
from datetime import datetime

import pytest

from gateway.slash_commands import GatewaySlashCommandsMixin
from gateway.session import Platform, SessionEntry, SessionStore
from gateway.session_lifecycle import SessionMetadataUpdateResult


class _Store:
    def __init__(self):
        self.entry = SimpleNamespace(session_key="k", metadata={})
        self.saved = []

    async def get_or_create_session(self, source):
        return self.entry

    async def set_session_metadata_if_idle(self, key, name, value, *, default=False):
        if getattr(self.entry, "active_turn_token", None):
            return SessionMetadataUpdateResult("active", self.entry.metadata.get(name, default), self.entry.metadata.get(name, default))
        self.entry.metadata[name] = value
        self.saved.append((key, name, value))
        return SessionMetadataUpdateResult("updated", not value, value)


class _FalseStore(_Store):
    async def set_session_metadata_if_idle(self, key, name, value, *, default=False):
        self.saved.append((key, name, value))
        return SessionMetadataUpdateResult("persistence_error", self.entry.metadata.get(name, default), self.entry.metadata.get(name, default))


@pytest.mark.asyncio
async def test_gateway_phone_command_persists_per_conversation_mode():
    store = _Store()
    runner = SimpleNamespace(
        async_session_store=store,
        _session_key_for_source=lambda source: "k",
        _is_session_running=lambda key: False,
    )
    args = {"value": "on"}
    event = SimpleNamespace(
        message="/p on",
        get_command_args=lambda: args["value"],
        source=SimpleNamespace(platform=Platform.TELEGRAM, chat_id="chat"),
    )

    reply = await GatewaySlashCommandsMixin._handle_phone_command(runner, event)

    assert "ON" in reply
    assert store.entry.metadata["phone_mode"] is True
    assert store.saved == [("k", "phone_mode", True)]

    event.message = "/phone"
    args["value"] = ""
    assert "ON" in await GatewaySlashCommandsMixin._handle_phone_command(runner, event)

    event.message = "/phone off"
    args["value"] = "off"
    await GatewaySlashCommandsMixin._handle_phone_command(runner, event)
    assert store.entry.metadata["phone_mode"] is False


@pytest.mark.asyncio
async def test_gateway_phone_command_preserves_mode_when_persistence_returns_false():
    store = _FalseStore()
    store.entry.metadata["phone_mode"] = False
    runner = SimpleNamespace(
        async_session_store=store,
        _session_key_for_source=lambda source: "k",
        _is_session_running=lambda key: False,
    )
    args = {"value": "on"}
    event = SimpleNamespace(
        get_command_args=lambda: args["value"],
        source=SimpleNamespace(platform=Platform.TELEGRAM, chat_id="chat"),
    )

    reply = await GatewaySlashCommandsMixin._handle_phone_command(runner, event)

    assert "could not be saved" in reply.lower()
    assert "OFF" in reply
    assert store.entry.metadata["phone_mode"] is False


@pytest.mark.asyncio
async def test_gateway_phone_toggle_rejected_while_turn_active_but_status_allowed():
    store = _Store()
    store.entry.metadata["phone_mode"] = False
    store.entry.active_turn_token = "turn-1"
    runner = SimpleNamespace(
        async_session_store=store,
        _session_key_for_source=lambda source: "k",
        _is_session_running=lambda key: True,
    )
    args = {"value": "status"}
    event = SimpleNamespace(
        get_command_args=lambda: args["value"],
        source=SimpleNamespace(platform=Platform.TELEGRAM, chat_id="chat"),
    )

    status = await GatewaySlashCommandsMixin._handle_phone_command(runner, event)
    assert "OFF" in status

    for action in ("on", "off"):
        args["value"] = action
        reply = await GatewaySlashCommandsMixin._handle_phone_command(runner, event)
        assert "active" in reply.lower()
        assert "OFF" in reply
    assert store.saved == []


def _bare_store(entry):
    store = object.__new__(SessionStore)
    store._lock = threading.Lock()
    store._entries = {entry.session_key: entry}
    store._loaded = True
    return store
def test_atomic_phone_metadata_keeps_old_value_when_save_raises():
    entry = SessionEntry("k", "sid", datetime.now(), datetime.now(), metadata={"phone_mode": False})
    store = _bare_store(entry)

    def fail_save(*args, **kwargs):
        raise OSError("disk full")

    store._save_entry = fail_save
    result = store.set_session_metadata_if_idle("k", "phone_mode", True, default=False)

    assert result.outcome == "persistence_error"
    assert result.effective_value is False
    assert entry.metadata["phone_mode"] is False


def test_atomic_phone_metadata_serializes_against_turn_start():
    entry = SessionEntry("k", "sid", datetime.now(), datetime.now(), metadata={"phone_mode": False})
    store = _bare_store(entry)
    entered_save = threading.Event()
    release_save = threading.Event()

    def save_candidate(*args, **kwargs):
        entered_save.set()
        assert release_save.wait(2)

    store._save_entry = save_candidate
    update_result = []
    turn_result = []
    update_thread = threading.Thread(
        target=lambda: update_result.append(store.set_session_metadata_if_idle("k", "phone_mode", True, default=False)))
    turn_thread = threading.Thread(target=lambda: turn_result.append(store.mark_turn_active("k")))
    update_thread.start()
    assert entered_save.wait(2)
    turn_thread.start()
    assert not turn_result
    release_save.set()
    update_thread.join(2)
    turn_thread.join(2)

    assert update_result[0].outcome == "updated"
    assert turn_result and turn_result[0]
    assert entry.metadata["phone_mode"] is True
