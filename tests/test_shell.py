from __future__ import annotations

import builtins
import json
import socket
import stat
import sys
import uuid
import urllib.error
from pathlib import Path

import pollyweb.msg as pollyweb_msg
import pytest

from pollyweb import Msg
from pollyweb_cli import cli
from pollyweb_cli.features import chat as chat_feature
from pollyweb_cli.features import test as test_feature
from pollyweb_cli.tools import transport as transport_tools

from tests.cli_test_helpers import (
    TEST_MSGS_DIR,
    VALID_BIND,
    VALID_WALLET_ID,
    DummyResponse,
    FakeChatConnection,
    FakeReadline,
    _setup_sync_env,
    make_echo_response_payload,
)

def test_shell_debug_prints_outbound_and_inbound_payloads(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
    )

    def fake_urlopen(request):
        return DummyResponse(b'{"ok":true}')

    commands = iter(["status --json target=prod", EOFError()])

    def fake_input(prompt):
        result = next(commands)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(builtins, "input", fake_input)

    exit_code = cli.main(["shell", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert "Outbound payload to https://pw.vault.example.com/inbox:" in captured.out
    assert "Subject: Shell@Domain" in captured.out
    assert "From: 123e4567-e89b-12d3-a456-426614174000" in captured.out
    assert "Command: status" in captured.out
    assert "Arguments:" in captured.out
    assert "json: target=prod" in captured.out
    assert "Binds:" not in captured.out
    assert "\n\nInbound payload:\n" in captured.out
    assert "Inbound payload:" in captured.out
    assert "ok: true" in captured.out
    assert captured.err == ""

def test_shell_sends_signed_messages_until_eof(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds = [
        {"Bind": "123e4567-e89b-12d3-a456-426614174000", "Domain": "vault.example.com"}
    ]
    binds_path.write_text(cli.yaml.safe_dump(binds), encoding="utf-8")
    requests = []
    prompts = []
    user_inputs = iter(["balance", "send 10 alice", EOFError()])

    def fake_input(prompt):
        prompts.append(prompt)
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(f"ok:{len(requests)}".encode("utf-8"))

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert prompts == [
        "pw:vault.example.com> ",
        "pw:vault.example.com> ",
        "pw:vault.example.com> ",
    ]
    assert len(requests) == 3
    init_body = requests[0].data.decode("utf-8")
    first_body = requests[1].data.decode("utf-8")
    second_body = requests[2].data.decode("utf-8")
    assert '"Subject":"Shell@Domain"' in init_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in init_body
    assert '"Command":"help"' in init_body
    assert '"Arguments":{}' in init_body
    assert '"Binds":' not in init_body
    assert '"Subject":"Shell@Domain"' in first_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in first_body
    assert '"Command":"balance"' in first_body
    assert '"Arguments":{}' in first_body
    assert '"Binds":' not in first_body
    assert '"Command":"send"' in second_body
    assert '"Arguments":{"0":"10","1":"alice"}' in second_body
    assert '"From":"123e4567-e89b-12d3-a456-426614174000"' in second_body

    captured = capsys.readouterr()
    assert captured.out == "ok:2\nok:3\n\n"
    assert captured.err == ""

def test_print_shell_response_colors_success_codes(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":200,"Message":"ok"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "green"

def test_print_shell_response_colors_error_codes(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":"503","Message":"down"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "bold red"

def test_print_shell_response_renders_string_body_as_markdown(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":200,"Body":"# Hello\\n\\n- item"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "green"

def test_print_shell_response_renders_string_message_as_markdown(monkeypatch):
    printed = []

    class FakeConsole:
        def print(self, payload, style=None):
            printed.append((payload, style))

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Code":404,"Message":"# Missing\\n\\n- help"}')

    assert len(printed) == 1
    rendered, style = printed[0]
    assert isinstance(rendered, cli.Markdown)
    assert style == "yellow"

def test_print_shell_response_prints_raw_payload_when_body_is_not_a_string(
    monkeypatch, capsys
):
    class FakeConsole:
        def print(self, payload, style=None):
            raise AssertionError("console rendering should not be used")

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response('{"Body":{"ok":true}}')

    captured = capsys.readouterr()
    assert captured.out == '{"Body":{"ok":true}}\n'

def test_print_shell_response_falls_back_to_plain_print_for_non_http_payloads(
    monkeypatch, capsys
):
    class FakeConsole:
        def print(self, payload, style=None):
            raise AssertionError("console rendering should not be used")

    monkeypatch.setattr(cli, "SHELL_CONSOLE", FakeConsole())

    cli.print_shell_response("ok:1")
    cli.print_shell_response('{"Other":"data"}')

    captured = capsys.readouterr()
    assert captured.out == 'ok:1\n{"Other":"data"}\n'

def test_parse_shell_command_splits_command_and_arguments():
    assert cli.parse_shell_command("balance") == ("balance", [])
    assert cli.parse_shell_command('send --amount 10 user=alice "two words"') == (
        "send",
        ["--amount", "10", "user=alice", "two words"],
    )

def test_get_shell_from_value_strips_bind_prefix():
    assert (
        cli.get_shell_from_value("Bind:123e4567-e89b-12d3-a456-426614174000")
        == "123e4567-e89b-12d3-a456-426614174000"
    )
    assert cli.get_shell_from_value("existing") == "existing"

def test_build_shell_arguments_maps_long_flag_to_dictionary_entry():
    assert cli.build_shell_arguments(["--all", "123"]) == {"all": "123"}

def test_build_shell_arguments_maps_short_flag_to_dictionary_entry():
    assert cli.build_shell_arguments(["-a", "123"]) == {"a": "123"}

def test_build_shell_arguments_maps_equals_token_to_dictionary_entry():
    assert cli.build_shell_arguments(["a=123"]) == {"a": "123"}

def test_build_shell_arguments_keeps_positional_arguments_indexed():
    assert cli.build_shell_arguments(["10", "alice"]) == {
        "0": "10",
        "1": "alice",
    }

def test_parse_shell_command_rejects_invalid_quoting():
    try:
        cli.parse_shell_command('"unterminated')
    except cli.UserFacingError as exc:
        assert "Invalid shell command" in str(exc)
    else:
        raise AssertionError("Expected UserFacingError for invalid shell command")

def test_is_shell_exit_command_matches_supported_aliases():
    for command in [
        "exit",
        "quit",
        "!q",
        "!quit",
        "!qa",
        "!qall",
        "!wq",
        "!x",
        "!quit!",
    ]:
        assert cli.is_shell_exit_command(command) is True

    assert cli.is_shell_exit_command("balance") is False
    assert cli.is_shell_exit_command("!status") is False

def test_shell_ignores_blank_commands_and_exits_on_keyboard_interrupt(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    user_inputs = iter(["   ", KeyboardInterrupt()])
    requests = []

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b"unexpected")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert len(requests) == 1
    init_body = requests[0].data.decode("utf-8")
    assert '"Command":"help"' in init_body
    assert '"Arguments":{}' in init_body
    captured = capsys.readouterr()
    assert captured.out == "\n"
    assert captured.err == ""

def test_shell_exits_without_sending_user_command_for_exit_aliases(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    history_path = history_dir / "vault.example.com.txt"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    user_inputs = iter(["!q"])
    requests = []

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(request)
        return DummyResponse(b"ok")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert len(requests) == 1
    assert '"Command":"help"' in requests[0].data.decode("utf-8")
    assert not history_path.exists()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""

def test_shell_stops_on_request_error(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    user_inputs = iter(["balance"])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(_request):
        raise urllib.error.URLError("connection dropped")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Shell request to vault.example.com failed: connection dropped" in captured.err

def test_shell_requires_bind_for_target_domain(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": "other", "Domain": "other.example.com"}]),
        encoding="utf-8",
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No bind stored for vault.example.com." in captured.err
    assert "Run `pw bind vault.example.com` first." in captured.err

def test_shell_anonymous_flag_skips_bind_requirement(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text("[]\n", encoding = "utf-8")
    user_inputs = iter([EOFError()])
    requests = []

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    def fake_urlopen(request):
        requests.append(cli.json.loads(request.data.decode("utf-8")))
        return DummyResponse(b'{"Shell":{"commands":[]}}')

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["shell", "--anonymous", "vault.example.com"])

    assert exit_code == 0
    assert requests[0]["Header"]["From"] == "Anonymous"
    captured = capsys.readouterr()
    assert captured.out == "\n"

def test_shell_loads_and_updates_domain_history(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    history_path = history_dir / "vault.example.com.txt"
    config_dir.mkdir()
    history_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    history_path.write_text("older balance\nolder send bob\n", encoding="utf-8")
    fake_readline = FakeReadline()
    user_inputs = iter(["fresh status", EOFError()])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(cli, "readline", fake_readline)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(b"ok")
    )

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert fake_readline.history_length == cli.SHELL_HISTORY_LIMIT
    assert fake_readline.history == [
        "older balance",
        "older send bob",
        "fresh status",
    ]
    assert history_path.read_text(encoding="utf-8") == (
        "older balance\nolder send bob\nfresh status\n"
    )
    captured = capsys.readouterr()
    assert captured.out == "ok\n\n"

def test_shell_history_is_scoped_per_domain_and_trimmed_to_last_twenty(monkeypatch, tmp_path):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    history_dir = config_dir / "history"
    config_dir.mkdir()
    history_dir.mkdir()
    key_pair = cli.KeyPair()
    private_key_path.write_bytes(key_pair.private_pem_bytes())
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump([{"Bind": VALID_BIND, "Domain": "vault.example.com"}]),
        encoding="utf-8",
    )
    vault_history_path = history_dir / "vault.example.com.txt"
    other_history_path = history_dir / "other.example.com.txt"
    vault_history_path.write_text(
        "\n".join(f"cmd-{index}" for index in range(19)) + "\n",
        encoding="utf-8",
    )
    other_history_path.write_text("other-cmd\n", encoding="utf-8")
    fake_readline = FakeReadline()
    user_inputs = iter(["cmd-19", "cmd-20", EOFError()])

    def fake_input(_prompt):
        value = next(user_inputs)
        if isinstance(value, BaseException):
            raise value
        return value

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "HISTORY_DIR", history_dir)
    monkeypatch.setattr(cli, "readline", fake_readline)
    monkeypatch.setattr(builtins, "input", fake_input)
    monkeypatch.setattr(
        cli.urllib.request, "urlopen", lambda request: DummyResponse(b"ok")
    )

    exit_code = cli.main(["shell", "vault.example.com"])

    assert exit_code == 0
    assert vault_history_path.read_text(encoding="utf-8").splitlines() == [
        *(f"cmd-{index}" for index in range(1, 19)),
        "cmd-19",
        "cmd-20",
    ]
    assert other_history_path.read_text(encoding="utf-8") == "other-cmd\n"

