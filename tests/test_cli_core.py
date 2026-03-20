from __future__ import annotations

import builtins
import json
import os
import socket
import stat
import subprocess
import sys
import uuid
import urllib.error
from pathlib import Path
from unittest.mock import patch

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

def test_dependency_contract_requires_pollyweb_release_with_unsigned_uuid_send_support():
    key_pair = cli.KeyPair()
    payloads = []

    def fake_post(url, body, *, timeout = 10.0):
        payloads.append(cli.json.loads(body.decode("utf-8")))
        return b'{"ok":true}'

    message = Msg(
        From = VALID_WALLET_ID,
        To = "vault.example.com",
        Subject = "Echo@Domain",
    )

    with patch("pollyweb.msg.post_json_bytes", side_effect = fake_post):
        assert message.send() == {"ok": True}

    assert payloads[0]["Header"]["From"] == VALID_WALLET_ID
    assert "Hash" not in payloads[0]
    assert "Signature" not in payloads[0]


def test_autouse_fixture_isolates_cli_profile_paths(tmp_path):
    fake_home = tmp_path / "home"

    assert cli.CONFIG_DIR == fake_home / ".pollyweb"
    assert cli.BINDS_PATH == fake_home / ".pollyweb" / "binds.yaml"
    assert transport_tools.DEFAULT_BINDS_PATH == fake_home / ".pollyweb" / "binds.yaml"
    assert Path(os.environ["HOME"]) == fake_home

def test_version_command_prints_installed_version(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", lambda argv: None)
    monkeypatch.setattr(cli, "get_installed_version", lambda _: "1.2.3")

    assert cli.main(["version"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "pw 1.2.3"
    assert captured.err == ""

def test_version_command_checks_for_upgrade_before_printing_version(monkeypatch, capsys):
    prompted = []

    def fake_preflight(argv):
        prompted.append(list(argv))
        return None

    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", fake_preflight)
    monkeypatch.setattr(cli, "get_installed_version", lambda _: "1.2.3")

    assert cli.main(["version"]) == 0
    assert prompted == [["version"]]
    captured = capsys.readouterr()
    assert captured.out.strip() == "pw 1.2.3"


def test_repo_root_pw_dev_launcher_runs_local_cli(tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok = True)

    result = subprocess.run(
        [str(Path(__file__).resolve().parents[1] / "pw-dev"), "version"],
        check = False,
        capture_output = True,
        text = True,
        env = {
            **os.environ,
            "HOME": str(fake_home),
            "USERPROFILE": str(fake_home),
        },
    )

    assert result.returncode == 0
    assert result.stdout.strip().startswith("pw ")
    assert "Upgraded from" not in result.stderr

def test_preflight_skips_when_no_newer_release(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.62")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.62")

    assert cli._maybe_upgrade_before_command(["bind", "vault.example.com"]) is None

def test_preflight_treats_dev_version_as_older_than_stable(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.dev43")
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.61")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)

    seen = []

    def fake_upgrade(argv, installed, latest):
        seen.append((list(argv), installed, latest))
        return 0

    monkeypatch.setattr(cli, "_upgrade_and_restart", fake_upgrade)

    assert cli._maybe_upgrade_before_command(["bind", "vault.example.com"]) == 0
    assert seen == [(["bind", "vault.example.com"], "0.1.dev43", "0.1.61")]

def test_requires_published_runtime_for_direct_url_install(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.118")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: True)

    assert cli._requires_published_runtime() is True

def test_preflight_reinstalls_latest_release_for_direct_url_runtime(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.118")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: True)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.118")

    seen = []

    def fake_upgrade(argv, installed, latest):
        seen.append((list(argv), installed, latest))
        return 0

    monkeypatch.setattr(cli, "_upgrade_and_restart", fake_upgrade)

    assert cli._maybe_upgrade_before_command(["echo", "vault.example.com"]) == 0
    assert seen == [(["echo", "vault.example.com"], "0.1.118", "0.1.118")]

def test_preflight_ignores_skip_env_for_non_pypi_runtime(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.dev43")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.61")
    monkeypatch.setenv(cli.SKIP_UPGRADE_CHECK_ENV, "1")

    seen = []

    def fake_upgrade(argv, installed, latest):
        seen.append((list(argv), installed, latest))
        return 0

    monkeypatch.setattr(cli, "_upgrade_and_restart", fake_upgrade)

    assert cli._maybe_upgrade_before_command(["bind", "vault.example.com"]) == 0
    assert seen == [(["bind", "vault.example.com"], "0.1.dev43", "0.1.61")]

def test_preflight_fails_closed_when_non_pypi_runtime_cannot_check_latest(
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.dev43")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: None)

    assert cli._maybe_upgrade_before_command(["bind", "vault.example.com"]) == 1
    captured = capsys.readouterr()
    assert (
        "Error: This pollyweb-cli runtime is not a published PyPI release, "
        "and the latest published release could not be determined."
    ) in captured.err

def test_get_latest_published_version_uses_uncached_json_request(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=0):
        seen["url"] = request.full_url
        seen["headers"] = {
            key.lower(): value
            for key, value in request.header_items()
        }
        return DummyResponse(b'{"info":{"version":"0.1.62"}}')

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    assert cli._get_latest_published_version() == "0.1.62"
    assert seen["url"].startswith(cli.PYPI_JSON_URL)
    assert "?_=" in seen["url"]
    assert seen["headers"]["accept"] == "application/json"
    assert seen["headers"]["cache-control"] == "no-cache"
    assert seen["headers"]["pragma"] == "no-cache"

def test_preflight_upgrades_and_reexecs_requested_command(monkeypatch):
    recorded: dict[str, object] = {}

    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.61")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.62")
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: False)

    def fake_run(command, check, stdout=None, stderr=None):
        recorded["run"] = command
        recorded["stdout"] = stdout
        recorded["stderr"] = stderr

        class Result:
            returncode = 0

        return Result()

    def fake_execve(executable, args, env):
        recorded["execve"] = (executable, args, env)
        raise SystemExit(0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.os, "execve", fake_execve)

    with pytest.raises(SystemExit) as exc:
        cli._maybe_upgrade_before_command(["bind", "vault.example.com"])

    assert exc.value.code == 0
    assert recorded["run"] == [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-U",
        "--disable-pip-version-check",
        "pollyweb-cli==0.1.62",
    ]
    assert recorded["stdout"] is cli.subprocess.DEVNULL
    assert recorded["stderr"] is cli.subprocess.DEVNULL
    executable, args, env = recorded["execve"]
    assert executable == sys.executable
    assert args == [sys.executable, "-m", "pollyweb_cli.cli", "bind", "vault.example.com"]
    assert env[cli.SKIP_UPGRADE_CHECK_ENV] == "1"

def test_preflight_shows_transient_upgrade_status_and_final_notice(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.61")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.62")
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)

    recorded: dict[str, object] = {}

    class FakeStatus:
        def __enter__(self):
            recorded["entered"] = True
            return self

        def __exit__(self, exc_type, exc, tb):
            recorded["exited"] = True
            return False

    class FakeConsole:
        def status(self, message, spinner):
            recorded["status"] = {
                "message": message,
                "spinner": spinner,
            }
            return FakeStatus()

    def fake_run(command, check, stdout=None, stderr=None):
        recorded["run"] = command
        recorded["stdout"] = stdout
        recorded["stderr"] = stderr

        class Result:
            returncode = 0

        return Result()

    def fake_execve(executable, args, env):
        raise SystemExit(0)

    monkeypatch.setattr(cli, "UPGRADE_CONSOLE", FakeConsole())
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli.os, "execve", fake_execve)

    with pytest.raises(SystemExit):
        cli._maybe_upgrade_before_command(["echo", "vault.example.com"])

    captured = capsys.readouterr()
    assert recorded["status"] == {
        "message": "Upgrading from v0.1.61 to v0.1.62",
        "spinner": "dots",
    }
    assert recorded["entered"] is True
    assert recorded["exited"] is True
    assert recorded["stdout"] is cli.subprocess.DEVNULL
    assert recorded["stderr"] is cli.subprocess.DEVNULL
    assert captured.err.replace("\x1b[2K", "").strip() == (
        "ⓘ Upgraded from v0.1.61 to v0.1.62"
    )

def test_install_upgrade_retries_once_before_failing(monkeypatch):
    commands = []
    returncodes = iter([1, 0])

    def fake_run(command, check, stdout=None, stderr=None):
        commands.append(command)

        class Result:
            returncode = next(returncodes)

        return Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_is_virtual_environment", lambda: True)

    assert cli._install_upgrade("0.1.72", "0.1.73", quiet = True) is True
    assert commands == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--disable-pip-version-check",
            "pollyweb-cli==0.1.73",
        ],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--disable-pip-version-check",
            "pollyweb-cli==0.1.73",
        ],
    ]

def test_install_upgrade_falls_back_to_user_install_outside_virtualenv(monkeypatch):
    commands = []
    returncodes = iter([1, 1, 0])

    def fake_run(command, check, stdout=None, stderr=None):
        commands.append(command)

        class Result:
            returncode = next(returncodes)

        return Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_is_virtual_environment", lambda: False)

    assert cli._install_upgrade("0.1.72", "0.1.73", quiet = True) is True
    assert commands == [
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--disable-pip-version-check",
            "pollyweb-cli==0.1.73",
        ],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--disable-pip-version-check",
            "pollyweb-cli==0.1.73",
        ],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "--disable-pip-version-check",
            "--user",
            "pollyweb-cli==0.1.73",
        ],
    ]

def test_cmd_upgrade_installs_latest_release(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.72")
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.73")
    monkeypatch.setattr(cli, "_install_upgrade", lambda installed, latest: True)

    assert cli.cmd_upgrade() == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Upgraded pollyweb-cli from 0.1.72 to 0.1.73."
    assert captured.err == ""

def test_cmd_upgrade_fails_when_latest_version_is_unavailable(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: None)

    assert cli.cmd_upgrade() == 1
    captured = capsys.readouterr()
    assert (
        "Error: Could not determine the latest published pollyweb-cli release."
        in captured.err
    )

def test_cmd_upgrade_returns_error_when_install_fails(monkeypatch):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.72")
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.73")
    monkeypatch.setattr(cli, "_install_upgrade", lambda installed, latest: False)

    assert cli.cmd_upgrade() == 1

def test_preflight_continues_when_upgrade_install_fails(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_get_cli_version", lambda: "0.1.72")
    monkeypatch.setattr(cli, "_distribution_uses_direct_url", lambda: False)
    monkeypatch.setattr(cli, "_get_latest_published_version", lambda: "0.1.73")
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: False)

    def fake_run(command, check, stdout=None, stderr=None):
        class Result:
            returncode = 1

        return Result()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli._maybe_upgrade_before_command(["bind", "vault.example.com"]) is None
    captured = capsys.readouterr()
    assert (
        "⚠️ Notice: Failed to upgrade pollyweb-cli to 0.1.73; "
        "continuing with installed 0.1.72."
    ) in captured.err

def test_main_checks_for_upgrade_before_running_command(monkeypatch):
    calls: list[list[str]] = []

    def fake_preflight(argv):
        calls.append(list(argv))
        return 0

    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", fake_preflight)

    assert cli.main(["bind", "vault.example.com"]) == 0
    assert calls == [["bind", "vault.example.com"]]

def test_main_upgrade_command_skips_preflight_and_runs_upgrade(monkeypatch):
    called = {"preflight": False, "upgrade": False}

    def fake_preflight(argv):
        called["preflight"] = True
        return None

    def fake_upgrade():
        called["upgrade"] = True
        return 0

    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", fake_preflight)
    monkeypatch.setattr(cli, "cmd_upgrade", fake_upgrade)

    assert cli.main(["upgrade"]) == 0
    assert called == {"preflight": False, "upgrade": True}

def test_parser_includes_upgrade_command():
    parser = cli.build_parser()

    args = parser.parse_args(["upgrade"])

    assert args.command == "upgrade"

def test_parser_includes_chat_command():
    parser = cli.build_parser()

    args = parser.parse_args(["chat"])

    assert args.command == "chat"
    assert args.domain is None
    assert args.debug is False

def test_parser_accepts_chat_debug_flag():
    parser = cli.build_parser()

    args = parser.parse_args(["chat", "--debug"])

    assert args.command == "chat"
    assert args.domain is None
    assert args.debug is True
    assert args.test is False

def test_parser_accepts_chat_test_flag():
    parser = cli.build_parser()

    args = parser.parse_args(["chat", "--test"])

    assert args.command == "chat"
    assert args.domain is None
    assert args.debug is False
    assert args.test is True

def test_parser_accepts_chat_domain_override():
    parser = cli.build_parser()

    args = parser.parse_args(["chat", "override.example.com", "--debug", "--test"])

    assert args.command == "chat"
    assert args.domain == "override.example.com"
    assert args.debug is True
    assert args.test is True

def test_parser_accepts_shared_unsigned_and_anonymous_flags():
    parser = cli.build_parser()

    msg_args = parser.parse_args(["msg", "--unsigned", "--anonymous", "To:vault.example.com", "Subject:Echo@Domain"])
    chat_args = parser.parse_args(["chat", "--unsigned", "--anonymous"])

    assert msg_args.unsigned is True
    assert msg_args.anonymous is True
    assert chat_args.unsigned is True
    assert chat_args.anonymous is True

def test_parser_accepts_msg_command():
    parser = cli.build_parser()

    args = parser.parse_args(["msg", "./message.yaml", "--debug", "--json"])

    assert args.command == "msg"
    assert args.message == ["./message.yaml"]
    assert args.debug is True
    assert args.json is True

def test_parser_accepts_test_command():
    parser = cli.build_parser()

    args = parser.parse_args(["test", "./test.yaml", "--debug", "--json"])

    assert args.command == "test"
    assert args.path == "./test.yaml"
    assert args.debug is True
    assert args.json is True


def test_parser_accepts_test_command_without_path():
    parser = cli.build_parser()

    args = parser.parse_args(["test", "--debug", "--json"])

    assert args.command == "test"
    assert args.path is None
    assert args.debug is True
    assert args.json is True


def test_parser_accepts_tests_command_alias():
    parser = cli.build_parser()

    args = parser.parse_args(["tests", "./test.yaml", "--debug", "--json"])

    assert args.command == "tests"
    assert args.path == "./test.yaml"
    assert args.debug is True
    assert args.json is True


def test_parser_accepts_echo_command():
    parser = cli.build_parser()

    args = parser.parse_args(["echo", "vault.example.com", "--debug", "--json"])

    assert args.command == "echo"
    assert args.domain == "vault.example.com"
    assert args.debug is True
    assert args.json is True

def test_print_debug_payload_wraps_long_unbroken_strings_as_literal_blocks(capsys):
    cli.print_debug_payload(
        "Outbound payload",
        {
            "Body": {"PublicKey": "A" * 96},
            "Signature": "B" * 96,
        },
    )

    captured = capsys.readouterr()
    assert "PublicKey: |" in captured.out
    assert "Signature: |" in captured.out
    assert "A" * 64 in captured.out
    assert "A" * 32 in captured.out
    assert "B" * 64 in captured.out
    assert "B" * 32 in captured.out

def test_print_debug_payload_wraps_public_key_even_when_shorter_than_width(capsys):
    cli.print_debug_payload(
        "Outbound payload",
        {
            "Body": {
                "PublicKey": "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv=="
            }
        },
    )

    captured = capsys.readouterr()
    assert "PublicKey: |" in captured.out
    assert "MCowBQYDK2VwAyEA1234567890abcdefghijklmnopqrstuv==" in captured.out

def test_main_renders_user_facing_errors_in_red(monkeypatch):
    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", lambda argv: None)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        cli,
        "cmd_echo",
        lambda domain, debug, json_output = False, unsigned = False, anonymous = False: (
            _ for _ in ()
        ).throw(cli.UserFacingError("boom")),
    )
    printed = []

    def fake_print(*args, **kwargs):
        printed.append((args, kwargs))

    monkeypatch.setattr(builtins, "print", fake_print)

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    assert printed == [
        (
            (f"{cli.ERROR_STYLE}Error: boom{cli.ERROR_STYLE_RESET}",),
            {"file": cli.sys.stderr},
        )
    ]

def test_main_renders_bind_errors_in_red(monkeypatch):
    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", lambda argv: None)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        cli,
        "cmd_bind",
        lambda domain, debug, json_output = False, unsigned = False, anonymous = False: (_ for _ in ()).throw(
            cli.UserFacingError(
                f"Could not bind {domain}. The server returned HTTP 500."
            )
        ),
    )
    printed = []

    def fake_print(*args, **kwargs):
        printed.append((args, kwargs))

    monkeypatch.setattr(builtins, "print", fake_print)

    exit_code = cli.main(["bind", "any-hoster.pollyweb.org"])

    assert exit_code == 1
    assert printed == [
        (
            (
                f"{cli.ERROR_STYLE}Error: Could not bind any-hoster.pollyweb.org. "
                f"The server returned HTTP 500.{cli.ERROR_STYLE_RESET}",
            ),
            {"file": cli.sys.stderr},
        )
    ]

def test_main_wraps_validation_errors_without_debug(monkeypatch):
    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", lambda argv: None)
    monkeypatch.setattr(cli.sys.stderr, "isatty", lambda: True)
    monkeypatch.setattr(
        cli,
        "cmd_echo",
        lambda domain, debug, unsigned = False, anonymous = False: (
            _ for _ in ()
        ).throw(cli.MsgValidationError("To must be a domain string or a UUID")),
    )
    printed = []

    def fake_print(*args, **kwargs):
        printed.append((args, kwargs))

    monkeypatch.setattr(builtins, "print", fake_print)

    exit_code = cli.main(["echo", "any-domain"])

    assert exit_code == 1
    assert printed == [
        (
            (
                f"{cli.ERROR_STYLE}Error: Invalid input. "
                "To must be a domain string or a UUID. "
                f"Please fix the command input and try again.{cli.ERROR_STYLE_RESET}",
            ),
            {"file": cli.sys.stderr},
        )
    ]

def test_main_prints_traceback_for_validation_errors_with_debug(
    monkeypatch, capsys
):
    monkeypatch.setattr(cli, "_maybe_upgrade_before_command", lambda argv: None)
    monkeypatch.setattr(
        cli,
        "cmd_echo",
        lambda domain, debug, unsigned = False, anonymous = False: (
            _ for _ in ()
        ).throw(cli.MsgValidationError("To must be a domain string or a UUID")),
    )

    exit_code = cli.main(["echo", "--debug", "any-domain"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Traceback (most recent call last):" in captured.err
    assert "To must be a domain string or a UUID" in captured.err
