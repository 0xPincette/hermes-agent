from hermes_cli.cli_commands_mixin import CLICommandsMixin
from hermes_cli.phone_mode import (
    PHONE_MODE_METADATA_KEY,
    augment_phone_message,
    parse_phone_command,
)


def test_phone_command_parser_supports_bare_alias_and_modes():
    assert parse_phone_command("/phone") == ("status", None)
    assert parse_phone_command("/p on") == ("on", None)
    assert parse_phone_command("/phone off") == ("off", None)
    assert parse_phone_command("/phone status") == ("status", None)


def test_phone_command_parser_rejects_extra_or_unknown_arguments():
    assert parse_phone_command("/phone maybe") == (None, "Usage: /phone [on|off|status]")
    assert parse_phone_command("/phone on now") == (None, "Usage: /phone [on|off|status]")


def test_phone_augmentation_is_api_local_and_keeps_original_message():
    original = "Delete the old database"
    augmented = augment_phone_message(original, enabled=True)
    assert original == "Delete the old database"
    assert augmented.endswith(original)
    assert "answer first" in augmented
    assert "preserve security warnings" in augmented
    assert augment_phone_message(original, enabled=False) == original


def test_phone_metadata_key_is_stable():
    assert PHONE_MODE_METADATA_KEY == "phone_mode"


def _phone_cli(db, *, enabled=False, agent_running=False, interactive_turn=False):
    output = []
    cli = type("PhoneCLI", (), {})()
    cli._phone_mode = enabled
    cli._session_db = db
    cli.session_id = "session-1"
    cli.model = "model"
    cli._agent_running = agent_running
    cli._interactive_turn = interactive_turn
    cli._console_print = output.append
    return cli, output


class _FailingPhoneStore:
    def get_session(self, session_id):
        return {"id": session_id}

    def patch_session_model_config(self, session_id, values):
        raise OSError("disk full")


def test_phone_toggle_keeps_previous_mode_and_reports_persistence_failure():
    cli, output = _phone_cli(_FailingPhoneStore(), enabled=False)

    CLICommandsMixin._handle_phone_command(cli, "/phone on")

    assert cli._phone_mode is False
    assert "failed" in output[-1].lower()
    assert "OFF" in output[-1]


def test_phone_toggle_is_refused_during_active_cli_turn():
    cli, output = _phone_cli(_FailingPhoneStore(), enabled=False, agent_running=True)

    CLICommandsMixin._handle_phone_command(cli, "/phone on")

    assert cli._phone_mode is False
    assert "active" in output[-1].lower()
    assert "OFF" in output[-1]
