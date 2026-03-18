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

def _materialize_inbound_wildcards(
    value
):
    """Replace test-only wildcard expectations with concrete response values."""

    if isinstance(value, dict):
        return {
            key: _materialize_inbound_wildcards(nested_value)
            for key, nested_value in value.items()
        }

    if isinstance(value, list):
        return [
            _materialize_inbound_wildcards(item)
            for item in value
        ]

    if value == "<uuid>":
        return str(uuid.uuid4())

    if value == "<str>":
        return "example-string"

    return value

def test_test_loads_wrapped_fixture_and_verifies_inbound(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  From: any-hoster.pollyweb.org\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Header":{"From":"any-hoster.pollyweb.org","To":"any-hoster.pollyweb.org","Subject":"Echo@Domain"},"Body":{"Extra":"ok"}}',
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_json_flag_keeps_success_output_concise(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Header":{"From":"any-hoster.pollyweb.org","To":"any-hoster.pollyweb.org","Subject":"Echo@Domain"},"Body":{"Extra":"ok"}}',
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", "--json", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_debug_json_passes_raw_debug_flag_to_transport(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    observed = {}
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        observed["debug"] = kwargs["debug"]
        observed["debug_json"] = kwargs["debug_json"]
        return (
            '{"Header":{"Subject":"Echo@Domain"}}',
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)
    monkeypatch.setattr(
        transport_tools,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", "--debug", "--json", str(test_path)])

    assert exit_code == 0
    assert observed == {
        "debug": True,
        "debug_json": True,
    }
    captured = capsys.readouterr()
    assert captured.out.splitlines()[-1] == f"✅ Passed: {test_path.stem}"

def test_test_resolves_bind_placeholder_from_stored_binds(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    test_path = tmp_path / "test.yaml"
    bind_value = "30ddc4c7-ba23-4bae-971c-2595143f69eb"

    config_dir.mkdir()
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": bind_value,
                    "Domain": "any-hoster.pollyweb.org",
                }
            ],
            sort_keys = False),
        encoding = "utf-8")
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "  From: '{BindOf(any-hoster.pollyweb.org)}'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        assert kwargs["from_value"] == bind_value
        return (
            '{"Header":{"From":"any-hoster.pollyweb.org","To":"any-hoster.pollyweb.org","Subject":"Echo@Domain"}}',
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_resolves_bind_placeholder_for_dom_alias(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    test_path = tmp_path / "test.yaml"
    bind_value = "30ddc4c7-ba23-4bae-971c-2595143f69eb"

    config_dir.mkdir()
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": bind_value,
                    "Domain": "any-hoster.pollyweb.org",
                }
            ],
            sort_keys = False),
        encoding = "utf-8")
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
            "  From: '{BindOf(any-hoster.dom)}'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        assert kwargs["domain"] == "any-hoster.pollyweb.org"
        assert kwargs["from_value"] == bind_value
        return (
            '{"Header":{"From":"any-hoster.pollyweb.org","To":"any-hoster.pollyweb.org","Subject":"Echo@Domain"}}',
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_reports_missing_bind_for_placeholder(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    binds_path = config_dir / "binds.yaml"
    test_path = tmp_path / "test.yaml"

    config_dir.mkdir()
    binds_path.write_text("[]\n", encoding = "utf-8")
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "  From: '{BindOf(any-hoster.pollyweb.org)}'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No bind stored for any-hoster.pollyweb.org." in captured.err
    assert "Run `pw bind any-hoster.pollyweb.org` first." in captured.err


def test_test_resolves_public_key_placeholder_from_wallet(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    test_path = tmp_path / "test.yaml"
    public_key_path = config_dir / "public.pem"
    key_pair = cli.KeyPair()
    expected_public_key = cli.serialize_public_key_value(
        key_pair.public_pem_bytes().decode("utf-8")
    )

    config_dir.mkdir()
    public_key_path.write_bytes(key_pair.public_pem_bytes())
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "  Body:\n"
            "    PublicKey: '<PublicKey>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        assert kwargs["body"]["PublicKey"] == expected_public_key
        return (
            '{"Header":{"From":"any-hoster.pollyweb.org","To":"any-hoster.pollyweb.org","Subject":"Echo@Domain"}}',
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"


def test_test_reports_missing_public_key_for_placeholder(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    test_path = tmp_path / "test.yaml"

    config_dir.mkdir()
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "  Body:\n"
            "    PublicKey: '<PublicKey>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        f"Missing PollyWeb public key in {config_dir / 'public.pem'}."
        in captured.err
    )
    assert "Run `pw config` first." in captured.err


def test_test_without_path_runs_pw_tests_yaml_files_in_alphabetical_order(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    first_path = tests_dir / "a-first.yaml"
    second_path = tests_dir / "b-second.yaml"
    observed_paths: list[str] = []

    tests_dir.mkdir()
    first_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    second_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    def fake_send_wallet_message(**kwargs):
        observed_paths.append(kwargs["subject"])
        return (
            json.dumps({"Header": {"Subject": kwargs["subject"]}}),
            None,
            "any-hoster.pollyweb.org",
        )

    def fake_load_message_test_fixture(
        path,
        binds_path,
        public_key_path
    ):
        return {
            "Outbound": {
                "To": "any-hoster.dom",
                "Subject": path.name,
            }
        }

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test"])

    assert exit_code == 0
    assert observed_paths == ["a-first.yaml", "b-second.yaml"]
    captured = capsys.readouterr()
    assert captured.out.splitlines() == [
        "✅ Passed: a-first",
        "✅ Passed: b-second",
    ]


def test_test_without_path_reports_missing_pw_tests_directory(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["test"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"No test path was provided and {tmp_path / 'pw-tests'} does not exist." in captured.err


@pytest.mark.parametrize(
    "fixture_path",
    sorted(TEST_MSGS_DIR.glob("*")),
    ids = lambda path: path.name)
def test_test_command_accepts_every_checked_in_test_message_fixture(
    monkeypatch,
    fixture_path,
    tmp_path,
    capsys
):
    # Load the checked-in fixture so the test follows the same wrapped
    # Outbound/Inbound contract documented for `pw test`.
    fixture = test_feature.load_message_test_fixture(
        fixture_path,
        tmp_path / "binds.yaml",
        tmp_path / "public.pem")

    # Build a JSON response that contains the expected inbound subset, because
    # `pw test` only requires the response to include those expected fields.
    inbound = _materialize_inbound_wildcards(fixture.get("Inbound") or {})
    response_payload = json.dumps(inbound)

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (response_payload, None, str(kwargs["domain"])))

    # Run the real CLI command for each fixture file in `test-msgs` so new
    # fixtures automatically get covered by this repository test.
    exit_code = cli.main(["test", str(fixture_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {fixture_path.stem}"

def test_test_reports_missing_expected_inbound_key(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(
        cli,
        "require_configured_keys",
        lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: ('{"Header":{"To":"vault.example.com"}}', None, "vault.example.com"))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Expected response.Subject to exist in the response." in captured.err

def test_test_accepts_missing_expected_inbound_key_when_fixture_value_is_empty(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Header:\n"
            "    Algorithm: ''\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: ('{"Header":{"Subject":"Echo@Domain"}}', None, "vault.example.com"))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_accepts_present_empty_expected_inbound_key(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Header:\n"
            "    Algorithm: ''\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Header":{"Subject":"Echo@Domain","Algorithm":""}}',
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_accepts_literal_double_quote_empty_marker_in_response(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Header:\n"
            "    Algorithm: ''\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        return (
            json.dumps(
                {
                    "Header": {
                        "Subject": "Echo@Domain",
                        "Algorithm": "''",
                    }
                }
            ),
            None,
            "vault.example.com",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_accepts_uuid_wildcard_in_inbound_expectation(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    actual_uuid = str(uuid.uuid4())
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Correlation: '<uuid>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            json.dumps(
                {
                    "Header": {
                        "Correlation": actual_uuid,
                    }
                }
            ),
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

def test_test_reports_invalid_uuid_for_uuid_wildcard(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Correlation: '<uuid>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Header":{"Correlation":"not-a-uuid"}}',
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Expected response.Correlation to be a valid UUID" in captured.err

def test_test_accepts_string_wildcard_in_inbound_expectation(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Body:\n"
            "    Status: '<str>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Body":{"Status":"delivered"}}',
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == f"✅ Passed: {test_path.stem}"

@pytest.mark.parametrize(
    ("response_payload", "expected_message"),
    [
        (
            '{"Body":{"Status":""}}',
            "Expected response.Body.Status to be a non-empty string",
        ),
        (
            '{"Body":{"Status":123}}',
            "Expected response.Body.Status to be a string",
        ),
        (
            '{"Body":{}}',
            "Expected response.Body.Status to exist in the response.",
        ),
    ],
)
def test_test_rejects_invalid_string_wildcard_values(
    monkeypatch, tmp_path, capsys, response_payload, expected_message
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Body:\n"
            "    Status: '<str>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            response_payload,
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert expected_message in captured.err

def test_test_reports_http_failures_with_fixture_path(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def raise_http_error(**kwargs):
        raise urllib.error.HTTPError(
            "https://pw.vault.example.com/inbox",
            502,
            "Bad Gateway",
            hdrs = None,
            fp = None)

    monkeypatch.setattr(test_feature, "send_wallet_message", raise_http_error)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "HTTP 502 Bad Gateway." in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out

def test_test_reports_inbound_error_details_for_http_failures(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def raise_http_error(**kwargs):
        error = urllib.error.HTTPError(
            "https://pw.vault.example.com/inbox",
            400,
            "Bad Request",
            hdrs = None,
            fp = None)
        setattr(
            error,
            "pollyweb_error_body",
            json.dumps(
                {
                    "error": (
                        "Legacy proxy request failed with HTTP 401: "
                        "{\"error\": \"Signature verification failed: Missing Selector\"}"
                    )
                }
            ),
        )
        raise error

    monkeypatch.setattr(test_feature, "send_wallet_message", raise_http_error)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "HTTP 400 Bad Request. Legacy proxy request failed with HTTP 401"
        in captured.err
    )
    assert "Signature verification failed: Missing Selector" in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out

def test_test_reports_dns_failures_without_http_code(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def raise_dns_error(**kwargs):
        raise urllib.error.URLError(
            socket.gaierror(8, "Name or service not known"))

    monkeypatch.setattr(test_feature, "send_wallet_message", raise_dns_error)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Could not resolve PollyWeb inbox host pw.vault.example.com" in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out
