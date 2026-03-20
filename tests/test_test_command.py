from __future__ import annotations

import json
import threading
import time
import re
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

    if value == "<int>":
        return 123

    if value == "<timestamp>":
        # Use a concrete Zulu timestamp matching the pollyweb header format
        return "2024-01-02T03:04:05.678Z"

    return value


def assert_passed_output(
    line: str,
    fixture_name: str
):
    """Assert that a `pw test` success line includes timing details."""

    assert re.fullmatch(
        rf"✅ Passed: {re.escape(fixture_name)} \(\d+ ms, \d+% latency\)",
        line,
    )


def assert_spinner_output(
    lifecycle: list[str],
    fixture_names: list[str],
    send_labels: list[str]
):
    """Assert that the per-fixture spinner label matches the display name."""

    expected_lifecycle: list[str] = []

    for fixture_name, send_label in zip(fixture_names, send_labels, strict = True):
        spinner_message = test_feature.format_test_spinner_message(fixture_name)
        expected_lifecycle.extend(
            [
                f"enter:{spinner_message}",
                send_label,
                f"exit:{spinner_message}",
            ]
        )

    assert lifecycle == expected_lifecycle


def assert_group_spinner_output(
    lifecycle: list[str],
    group_name: str,
    send_labels: list[str]
):
    """Assert that one parallel group uses a single shared spinner label."""

    spinner_message = test_feature.format_test_group_spinner_message(group_name)
    expected_lifecycle = [f"enter:{spinner_message}", *send_labels, f"exit:{spinner_message}"]
    assert lifecycle[:len(expected_lifecycle)] == expected_lifecycle


def test_build_parallel_test_status_message_renders_file_hierarchy():
    message = test_feature.build_parallel_test_status_message(
        [
            ("files 03-*", "03-first"),
            ("files 03-*", "03-second"),
        ]
    )

    assert message == (
        "files 03-*\n"
        "03-first\n"
        "03-second"
    )


def test_build_parallel_test_status_message_renders_folder_and_file_hierarchy():
    message = test_feature.build_parallel_test_status_message(
        [
            ("folders 01-*", "files 01-alpha/10-*", "01-alpha/10-fast"),
            ("folders 01-*", "files 01-beta/10-*", "01-beta/10-slow"),
        ]
    )

    assert message == (
        "folders 01-*\n"
        "files 01-alpha/10-*\n"
        "  01-alpha/10-fast\n"
        "files 01-beta/10-*\n"
        "  01-beta/10-slow"
    )


def test_build_parallel_test_status_message_bubbles_success_to_groups():
    message = test_feature.build_parallel_test_status_message(
        [
            ("files 02-*", "✅ Passed: 2-PublicKeyA (435 ms, 99% latency)"),
            ("files 02-*", "✅ Passed: 2-PublicKeyB (930 ms, 53% latency)"),
        ]
    )

    assert message == (
        "✅ Passed: files 02-*\n"
        "✅ Passed: 2-PublicKeyA (435 ms, 99% latency)\n"
        "✅ Passed: 2-PublicKeyB (930 ms, 53% latency)"
    )


def test_format_test_group_success_message_uses_group_label():
    assert test_feature.format_test_group_success_message("files 02-*") == (
        "✅ Passed: files 02-*"
    )


def test_build_test_group_success_lines_keeps_child_results_visible():
    assert test_feature.build_test_group_success_lines(
        "files 02-*",
        [
            "✅ Passed: 2-PublicKeyA (435 ms, 99% latency)",
            "✅ Passed: 2-PublicKeyB (930 ms, 53% latency)",
        ],
    ) == [
        "✅ Passed: files 02-*",
        "  ✅ Passed: 2-PublicKeyA (435 ms, 99% latency)",
        "  ✅ Passed: 2-PublicKeyB (930 ms, 53% latency)",
    ]


def test_parallel_status_renderer_keeps_console_writes_off_worker_threads(
    monkeypatch
):
    renderer = test_feature.ParallelTestStatusRenderer()
    worker_thread_ids: list[int] = []
    status_thread_ids: list[int] = []
    lifecycle: list[str] = []

    class FakeStatus:
        """Capture which thread owns the terminal status lifecycle."""

        def __init__(
            self,
            message: str
        ):
            """Store the initial message for inspection."""

            self.message = message

        def __enter__(self):
            """Record the thread that opens the shared status."""

            status_thread_ids.append(threading.get_ident())
            lifecycle.append(f"enter:{self.message}")
            return self

        def update(
            self,
            message: str
        ):
            """Record the thread that updates the shared status."""

            status_thread_ids.append(threading.get_ident())
            lifecycle.append(f"update:{message}")

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record the thread that closes the shared status."""

            status_thread_ids.append(threading.get_ident())
            lifecycle.append("exit")
            return False

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def worker(
        path: tuple[str, ...],
        release_event: threading.Event
    ):
        """Push one worker-owned path until the test releases it."""

        worker_thread_ids.append(threading.get_ident())
        token = renderer.push(path)
        assert release_event.wait(timeout = 5)
        renderer.pop(token)

    release_first = threading.Event()
    release_second = threading.Event()
    first_worker = threading.Thread(
        target = worker,
        args = (("folders 01-*", "files 01-alpha/10-*", "01-alpha/10-fast"), release_first),
        daemon = True,
    )
    second_worker = threading.Thread(
        target = worker,
        args = (("folders 01-*", "files 01-beta/10-*", "01-beta/10-slow"), release_second),
        daemon = True,
    )
    first_worker.start()
    second_worker.start()

    deadline = time.time() + 1
    while time.time() < deadline:
        if any(entry.startswith("update:") for entry in lifecycle):
            break
        time.sleep(0.01)

    release_first.set()
    release_second.set()
    first_worker.join(timeout = 2)
    second_worker.join(timeout = 2)

    deadline = time.time() + 1
    while time.time() < deadline:
        if renderer._render_thread is None:
            break
        time.sleep(0.01)

    assert lifecycle[0].startswith("enter:folders 01-*")
    assert any(
        "files 01-alpha/10-*" in entry and "files 01-beta/10-*" in entry
        for entry in lifecycle
    )
    assert lifecycle[-1] == "exit"
    assert status_thread_ids
    assert set(status_thread_ids).isdisjoint(worker_thread_ids)


def test_parallel_status_renderer_waits_for_last_status_close(monkeypatch):
    renderer = test_feature.ParallelTestStatusRenderer()
    lifecycle: list[str] = []
    release_exit = threading.Event()

    class FakeStatus:
        """Delay status teardown so the caller must wait for shutdown."""

        def __init__(
            self,
            message: str
        ):
            """Store the message for parity with the real Rich status."""

            self.message = message

        def __enter__(self):
            """Record the status start."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def update(
            self,
            message: str
        ):
            """Accept later tree updates."""

            lifecycle.append(f"update:{message}")

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Hold exit long enough to prove `pop()` waits for it."""

            assert release_exit.wait(timeout = 5)
            lifecycle.append("exit")
            return False

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    token = renderer.push(("files 02-*", "02-sample"))
    deadline = time.time() + 1
    while time.time() < deadline:
        if lifecycle:
            break
        time.sleep(0.01)
    assert lifecycle[0].startswith("enter:files 02-*")

    exit_finished = threading.Event()

    def pop_last_token():
        """Pop the last active status path."""

        renderer.pop(token)
        exit_finished.set()

    pop_thread = threading.Thread(target = pop_last_token, daemon = True)
    pop_thread.start()
    time.sleep(0.05)
    assert not exit_finished.is_set()
    release_exit.set()
    pop_thread.join(timeout = 2)
    assert exit_finished.is_set()
    assert renderer._render_thread is None
    assert lifecycle[-1] == "exit"

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)


def test_test_shows_spinner_while_sending(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    lifecycle: list[str] = []
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    class FakeStatus:
        """Capture the status lifecycle around one fixture send."""

        def __init__(
            self,
            message: str
        ):
            """Store the status message for lifecycle assertions."""

            self.message = message

        def __enter__(self):
            """Record when the spinner starts."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record when the spinner stops."""

            lifecycle.append(f"exit:{self.message}")
            return False

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def fake_send_wallet_message(**kwargs):
        lifecycle.append("send")
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
    assert_spinner_output(
        lifecycle,
        [test_path.stem],
        ["send"])
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)


def test_test_without_path_shows_one_spinner_per_fixture(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    lifecycle: list[str] = []

    tests_dir.mkdir()
    (tests_dir / "a-first.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (tests_dir / "b-second.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    class FakeStatus:
        """Capture one status context per fixture send."""

        def __init__(
            self,
            message: str
        ):
            """Store the spinner message for assertions."""

            self.message = message

        def __enter__(self):
            """Record spinner start for one fixture."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record spinner stop for one fixture."""

            lifecycle.append(f"exit:{self.message}")
            return False

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def fake_send_wallet_message(**kwargs):
        lifecycle.append(f"send:{kwargs['subject']}")
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
    assert_spinner_output(
        lifecycle,
        ["a-first", "b-second"],
        ["send:a-first.yaml", "send:b-second.yaml"])
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 2
    assert_passed_output(lines[0], "a-first")
    assert_passed_output(lines[1], "b-second")


def test_test_without_path_shows_nested_fixture_path_in_spinner(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    nested_path = tests_dir / "nested" / "fixture.yaml"
    lifecycle: list[str] = []

    nested_path.parent.mkdir(parents = True)
    nested_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    class FakeStatus:
        """Capture the spinner message for one nested fixture send."""

        def __init__(
            self,
            message: str
        ):
            """Store the spinner message for assertions."""

            self.message = message

        def __enter__(self):
            """Record spinner start for the nested fixture."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record spinner stop for the nested fixture."""

            lifecycle.append(f"exit:{self.message}")
            return False

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def fake_send_wallet_message(**kwargs):
        lifecycle.append("send")
        return (
            json.dumps({"Header": {"Subject": kwargs["subject"]}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test"])

    assert exit_code == 0
    assert_spinner_output(
        lifecycle,
        ["nested/fixture"],
        ["send"])
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), "nested/fixture")


def test_extract_test_total_seconds_prefers_wrapped_response_meta_total_ms():
    payload = json.dumps(
        {
            "Meta": {
                "TotalMs": 80,
            },
            "Response": {
                "Meta": {
                    "TotalMs": 420,
                },
            },
        }
    )

    assert test_feature.extract_test_total_seconds(
        payload,
        measured_total_seconds = 0.2,
    ) == pytest.approx(0.42)


def test_extract_test_total_seconds_keeps_larger_local_duration():
    payload = json.dumps(
        {
            "Response": {
                "Meta": {
                    "TotalMs": 120,
                },
            },
        }
    )

    assert test_feature.extract_test_total_seconds(
        payload,
        measured_total_seconds = 0.35,
    ) == pytest.approx(0.35)


def test_extract_test_latency_seconds_uses_wrapped_response_total_ms():
    payload = json.dumps(
        {
            "Response": {
                "Meta": {
                    "TotalMs": 252,
                },
            },
        }
    )

    assert test_feature.extract_test_latency_seconds(
        payload,
        total_seconds = 0.56,
        network_seconds = 0.55,
    ) == pytest.approx(0.308)


def test_test_success_output_uses_wrapped_response_total_ms_for_latency_share(
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
    perf_counter_values = iter([10.0, 10.56])
    monkeypatch.setattr(
        test_feature.time,
        "perf_counter",
        lambda: next(perf_counter_values))

    def fake_send_wallet_message(**kwargs):
        kwargs["timing"]["network_seconds"] = 0.55
        return (
            json.dumps(
                {
                    "Request": {},
                    "Response": {
                        "Meta": {
                            "TotalMs": 252,
                        },
                        "Header": {
                            "Subject": "Echo@Domain",
                        },
                    },
                },
                separators = (",", ":"),
            ),
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
    assert captured.out.strip() == "✅ Passed: test (560 ms, 55% latency)"

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
    assert_passed_output(captured.out.splitlines()[-1], test_path.stem)


def test_test_accepts_long_wrapped_outbound_json_without_path_probe_failure(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  Header:\n"
            "    To: any-streamer.dom\n"
            "    Subject: Proxy@Domain\n"
            "  Body:\n"
            "    Header:\n"
            "      To: any-buffer.dom\n"
            "      Subject: Push@Buffer\n"
            "    Body:\n"
            "      Queue: ab594eec-8244-4159-8f0c-cd2f07700a1e\n"
            "      Subscriber: any-subscriber.dom\n"
            "      Message: my-encrypted-content-here\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    def fake_send_wallet_message(**kwargs):
        assert kwargs["domain"] == "any-streamer.pollyweb.org"
        assert kwargs["subject"] == "Proxy@Domain"
        assert kwargs["body"] == {
            "Header": {
                "To": "any-buffer.dom",
                "Subject": "Push@Buffer",
            },
            "Body": {
                "Queue": "ab594eec-8244-4159-8f0c-cd2f07700a1e",
                "Subscriber": "any-subscriber.dom",
                "Message": "my-encrypted-content-here",
            },
        }
        return (
            '{"Header":{"Subject":"Proxy@Domain"}}',
            None,
            "any-streamer.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)


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
    lines = captured.out.splitlines()
    assert len(lines) == 2
    assert_passed_output(lines[0], "a-first")
    assert_passed_output(lines[1], "b-second")


def test_test_without_path_runs_nested_pw_tests_yaml_files_in_sorted_order(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    nested_dir = tests_dir / "nested"
    deep_dir = nested_dir / "deeper"
    observed_paths: list[str] = []

    tests_dir.mkdir()
    nested_dir.mkdir()
    deep_dir.mkdir()
    (tests_dir / "b-second.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (nested_dir / "a-first.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (deep_dir / "c-third.yaml").write_text(
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
                "Subject": path.relative_to(tests_dir).as_posix(),
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
    assert observed_paths == [
        "b-second.yaml",
        "nested/a-first.yaml",
        "nested/deeper/c-third.yaml",
    ]
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 3
    assert_passed_output(lines[0], "b-second")
    assert_passed_output(lines[1], "nested/a-first")
    assert_passed_output(lines[2], "nested/deeper/c-third")


def test_test_without_debug_runs_same_folder_numeric_prefix_group_in_parallel(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    first_path = tests_dir / "03-first.yaml"
    second_path = tests_dir / "03-second.yaml"
    third_path = tests_dir / "04-third.yaml"
    started_subjects: list[str] = []
    completed_subjects: list[str] = []
    lifecycle: list[str] = []
    release_group = threading.Event()
    parallel_ready = threading.Event()
    started_lock = threading.Lock()

    tests_dir.mkdir()
    for path in (first_path, second_path, third_path):
        path.write_text(
            (
                "Outbound:\n"
                "  To: any-hoster.dom\n"
                "  Subject: Echo@Domain\n"
            ),
            encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    class FakeStatus:
        """Capture the shared spinner lifecycle for one parallel batch."""

        def __init__(
            self,
            message: str
        ):
            """Store the spinner message for assertions."""

            self.message = message

        def __enter__(self):
            """Record the start of the group spinner."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record the end of the group spinner."""

            lifecycle.append(f"exit:{self.message}")
            return False

        def update(
            self,
            message: str
        ):
            """Record in-place tree updates."""

            lifecycle.append(f"update:{message}")

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

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

    def fake_send_wallet_message(**kwargs):
        subject = kwargs["subject"]
        with started_lock:
            started_subjects.append(subject)
            lifecycle.append(f"send:{subject}")
            if {
                "03-first.yaml",
                "03-second.yaml",
            }.issubset(set(started_subjects)):
                parallel_ready.set()

        if subject.startswith("03-"):
            assert parallel_ready.wait(timeout = 1)
            assert release_group.wait(timeout = 5)

        completed_subjects.append(subject)
        return (
            json.dumps({"Header": {"Subject": subject}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    cli_thread = threading.Thread(
        target = lambda: cli.main(["tests"]),
        daemon = True)
    cli_thread.start()

    assert parallel_ready.wait(timeout = 1)
    assert set(started_subjects[:2]) == {
        "03-first.yaml",
        "03-second.yaml",
    }
    assert completed_subjects == []

    release_group.set()
    cli_thread.join(timeout = 2)
    assert not cli_thread.is_alive()
    assert set(completed_subjects[:2]) == {
        "03-first.yaml",
        "03-second.yaml",
    }
    assert completed_subjects[2:] == ["04-third.yaml"]

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines == [
        "✅ Passed: files 03-*",
        "  ✅ Passed: 03-first (0 ms, 0% latency)",
        "  ✅ Passed: 03-second (0 ms, 0% latency)",
        "✅ Passed: 04-third (0 ms, 0% latency)",
    ]
    assert {
        entry
        for entry in lifecycle
        if entry.startswith("send:")
    } >= {
        "send:03-first.yaml",
        "send:03-second.yaml",
    }


def test_test_parallel_group_prints_completed_success_before_group_finishes(
    monkeypatch, tmp_path
):
    tests_dir = tmp_path / "pw-tests"
    first_path = tests_dir / "03-fast.yaml"
    second_path = tests_dir / "03-slow.yaml"
    started_subjects: list[str] = []
    status_messages: list[str] = []
    release_slow = threading.Event()
    both_started = threading.Event()
    started_lock = threading.Lock()
    tests_dir.mkdir()
    for path in (first_path, second_path):
        path.write_text(
            (
                "Outbound:\n"
                "  To: any-hoster.dom\n"
                "  Subject: Echo@Domain\n"
            ),
            encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    class FakeStatus:
        """Suppress terminal spinner rendering while keeping lifecycle valid."""

        def __init__(
            self,
            message: str
        ):
            """Store the status message for compatibility."""

            self.message = message

        def __enter__(self):
            """Enter the fake spinner context."""

            status_messages.append(self.message)
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Exit the fake spinner context."""

            return False

        def update(
            self,
            message: str
        ):
            """Capture in-place status replacements."""

            status_messages.append(message)

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def fake_send_wallet_message(**kwargs):
        subject = kwargs["subject"]
        with started_lock:
            started_subjects.append(subject)
            if len(started_subjects) == 2:
                both_started.set()

        if subject == "03-slow.yaml":
            assert both_started.wait(timeout = 1)
            assert release_slow.wait(timeout = 5)

        return (
            json.dumps({"Header": {"Subject": subject}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    cli_thread = threading.Thread(
        target = lambda: cli.main(["tests"]),
        daemon = True)
    cli_thread.start()

    assert both_started.wait(timeout = 1)

    release_slow.set()
    cli_thread.join(timeout = 2)
    assert not cli_thread.is_alive()
    assert status_messages or started_subjects


def test_test_without_debug_runs_same_prefix_subfolders_in_parallel(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    first_dir = tests_dir / "03-alpha"
    second_dir = tests_dir / "03-beta"
    third_dir = tests_dir / "04-gamma"
    started_targets: list[str] = []
    completed_targets: list[str] = []
    lifecycle: list[str] = []
    release_group = threading.Event()
    parallel_ready = threading.Event()
    started_lock = threading.Lock()

    (first_dir / "child").mkdir(parents = True)
    second_dir.mkdir(parents = True)
    third_dir.mkdir(parents = True)
    (first_dir / "child" / "a.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (second_dir / "b.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (third_dir / "c.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    class FakeStatus:
        """Capture the shared spinner lifecycle for one directory batch."""

        def __init__(
            self,
            message: str
        ):
            """Store the spinner message for assertions."""

            self.message = message

        def __enter__(self):
            """Record the start of the group spinner."""

            lifecycle.append(f"enter:{self.message}")
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """Record the end of the group spinner."""

            lifecycle.append(f"exit:{self.message}")
            return False

        def update(
            self,
            message: str
        ):
            """Record in-place tree updates."""

            lifecycle.append(f"update:{message}")

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    def fake_send_wallet_message(**kwargs):
        subject = kwargs["subject"]
        with started_lock:
            started_targets.append(subject)
            lifecycle.append(f"send:{subject}")
            if {
                "03-alpha/child/a.yaml",
                "03-beta/b.yaml",
            }.issubset(set(started_targets)):
                parallel_ready.set()

        if subject in {"03-alpha/child/a.yaml", "03-beta/b.yaml"}:
            assert parallel_ready.wait(timeout = 1)
            assert release_group.wait(timeout = 5)

        completed_targets.append(subject)
        return (
            json.dumps({"Header": {"Subject": subject}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    def fake_load_message_test_fixture(
        path,
        binds_path,
        public_key_path
    ):
        return {
            "Outbound": {
                "To": "any-hoster.dom",
                "Subject": path.relative_to(tests_dir).as_posix(),
            }
        }

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)

    cli_thread = threading.Thread(
        target = lambda: cli.main(["tests"]),
        daemon = True)
    cli_thread.start()

    assert parallel_ready.wait(timeout = 1)
    assert set(started_targets[:2]) == {"03-alpha/child/a.yaml", "03-beta/b.yaml"}

    release_group.set()
    cli_thread.join(timeout = 2)
    assert not cli_thread.is_alive()
    assert set(completed_targets[:2]) == {"03-alpha/child/a.yaml", "03-beta/b.yaml"}
    assert completed_targets[2:] == ["04-gamma/c.yaml"]

    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert lines == [
        "✅ Passed: folders 03-*",
        "  ✅ Passed: 03-alpha/child/a (0 ms, 0% latency)",
        "  ✅ Passed: 03-beta/b (0 ms, 0% latency)",
        "✅ Passed: 04-gamma/c (0 ms, 0% latency)",
    ]
    assert {
        entry
        for entry in lifecycle
        if entry.startswith("send:")
    } >= {
        "send:03-alpha/child/a.yaml",
        "send:03-beta/b.yaml",
    }


def test_test_parallel_folder_group_prints_nested_success_before_sibling_folder_finishes(
    monkeypatch, tmp_path
):
    tests_dir = tmp_path / "pw-tests"
    first_dir = tests_dir / "01-alpha"
    second_dir = tests_dir / "01-beta"
    status_messages: list[str] = []
    release_slow = threading.Event()
    both_started = threading.Event()
    started_subjects: list[str] = []
    started_lock = threading.Lock()
    first_dir.mkdir(parents = True)
    second_dir.mkdir(parents = True)
    (first_dir / "10-fast.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (second_dir / "10-slow.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

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

    def fake_send_wallet_message(**kwargs):
        subject = kwargs["subject"]
        with started_lock:
            started_subjects.append(subject)
            if len(started_subjects) == 2:
                both_started.set()

        if subject == "10-slow.yaml":
            assert both_started.wait(timeout = 1)
            assert release_slow.wait(timeout = 5)

        return (
            json.dumps({"Header": {"Subject": subject}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    class FakeStatus:
        """Capture in-place updates for nested parallel folder runs."""

        def __init__(
            self,
            message: str
        ):
            """Store the initial message."""

            self.message = message

        def __enter__(self):
            """Record the initial tree render."""

            status_messages.append(self.message)
            return self

        def __exit__(
            self,
            exc_type,
            exc,
            tb
        ):
            """End the fake status context."""

            return False

        def update(
            self,
            message: str
        ):
            """Record later tree updates."""

            status_messages.append(message)

    monkeypatch.setattr(
        test_feature.DEBUG_CONSOLE,
        "status",
        lambda message: FakeStatus(message))

    cli_thread = threading.Thread(
        target = lambda: cli.main(["tests"]),
        daemon = True)
    cli_thread.start()

    assert both_started.wait(timeout = 1)

    release_slow.set()
    cli_thread.join(timeout = 2)
    assert not cli_thread.is_alive()
    assert status_messages or started_subjects


def test_test_parallel_folder_failure_reports_nested_fixture_path(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    failing_path = tests_dir / "01-alpha" / "10-drop.yaml"

    failing_path.parent.mkdir(parents = True)
    failing_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    def raise_http_error(**kwargs):
        raise urllib.error.HTTPError(
            "https://pw.any-hoster.pollyweb.org/inbox",
            502,
            "Bad Gateway",
            hdrs = None,
            fp = None)

    monkeypatch.setattr(test_feature, "send_wallet_message", raise_http_error)

    exit_code = cli.main(["test"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "❌ Failed: 01-alpha/10-drop" in captured.out


def test_test_debug_keeps_same_folder_numeric_prefix_group_sequential(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    first_path = tests_dir / "03-first.yaml"
    second_path = tests_dir / "03-second.yaml"
    observed_subjects: list[str] = []

    tests_dir.mkdir()
    for path in (first_path, second_path):
        path.write_text(
            (
                "Outbound:\n"
                "  To: any-hoster.dom\n"
                "  Subject: Echo@Domain\n"
            ),
            encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

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

    def fake_send_wallet_message(**kwargs):
        observed_subjects.append(kwargs["subject"])
        return (
            json.dumps({"Header": {"Subject": kwargs["subject"]}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message)

    exit_code = cli.main(["tests", "--debug"])

    assert exit_code == 0
    assert observed_subjects == ["03-first.yaml", "03-second.yaml"]
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 2
    assert_passed_output(lines[0], "03-first")
    assert_passed_output(lines[1], "03-second")


def test_test_with_explicit_directory_runs_yaml_files_in_sorted_order(
    monkeypatch, tmp_path, capsys
):
    fixtures_dir = tmp_path / "fixtures"
    nested_dir = fixtures_dir / "nested"
    deep_dir = nested_dir / "deeper"
    observed_paths: list[str] = []

    fixtures_dir.mkdir()
    nested_dir.mkdir()
    deep_dir.mkdir()
    (fixtures_dir / "b-second.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (nested_dir / "a-first.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (deep_dir / "c-third.yaml").write_text(
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
                "Subject": path.relative_to(fixtures_dir).as_posix(),
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

    exit_code = cli.main(["test", str(fixtures_dir)])

    assert exit_code == 0
    assert observed_paths == [
        "b-second.yaml",
        "nested/a-first.yaml",
        "nested/deeper/c-third.yaml",
    ]
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 3
    assert_passed_output(lines[0], "fixtures/b-second")
    assert_passed_output(lines[1], "fixtures/nested/a-first")
    assert_passed_output(lines[2], "fixtures/nested/deeper/c-third")


def test_test_with_explicit_directory_reports_missing_yaml_fixtures(
    monkeypatch, tmp_path, capsys
):
    fixtures_dir = tmp_path / "fixtures"

    fixtures_dir.mkdir()
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())

    exit_code = cli.main(["test", str(fixtures_dir)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"No YAML test fixtures were found in {fixtures_dir}." in captured.err


def test_test_with_named_pw_tests_subdirectory_runs_nested_yaml_files(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    fixtures_dir = tests_dir / "bla"
    nested_dir = fixtures_dir / "nested"
    observed_paths: list[str] = []

    nested_dir.mkdir(parents = True)
    (fixtures_dir / "b-second.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8")
    (nested_dir / "a-first.yaml").write_text(
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
                "Subject": path.relative_to(fixtures_dir).as_posix(),
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

    exit_code = cli.main(["test", "bla"])

    assert exit_code == 0
    assert observed_paths == [
        "b-second.yaml",
        "nested/a-first.yaml",
    ]
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert len(lines) == 2
    assert_passed_output(lines[0], "bla/b-second")
    assert_passed_output(lines[1], "bla/nested/a-first")


def test_test_named_pw_tests_subdirectory_does_not_override_explicit_file(
    monkeypatch, tmp_path, capsys
):
    tests_dir = tmp_path / "pw-tests"
    fallback_dir = tests_dir / "bla"
    explicit_file = tmp_path / "bla"
    loaded_paths: list[Path] = []

    fallback_dir.mkdir(parents = True)
    (fallback_dir / "ignored.yaml").write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: ignored\n"
        ),
        encoding = "utf-8")
    explicit_file.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: explicit\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    def fake_load_message_test_fixture(
        path,
        binds_path,
        public_key_path
    ):
        loaded_paths.append(path)
        return {
            "Outbound": {
                "To": "any-hoster.dom",
                "Subject": "explicit",
            }
        }

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            json.dumps({"Header": {"Subject": kwargs["subject"]}}),
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", "bla"])

    assert exit_code == 0
    assert loaded_paths == [Path("bla")]
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), "bla")


def test_get_test_fixture_display_name_includes_nested_subfolders(monkeypatch, tmp_path):
    tests_dir = tmp_path / "pw-tests"
    nested_path = tests_dir / "nested" / "deeper" / "fixture.yaml"

    nested_path.parent.mkdir(parents = True)
    monkeypatch.chdir(tmp_path)

    assert test_feature.get_test_fixture_display_name(nested_path) == (
        "nested/deeper/fixture"
    )


def test_get_test_fixture_display_name_keeps_explicit_non_nested_path_short(
    monkeypatch, tmp_path
):
    fixture_path = tmp_path / "fixture.yaml"

    monkeypatch.chdir(tmp_path)

    assert test_feature.get_test_fixture_display_name(fixture_path) == "fixture"


def test_get_test_fixture_display_name_includes_parent_for_explicit_subfolder_path(
    monkeypatch, tmp_path
):
    fixture_path = tmp_path / "nested" / "fixture.yaml"

    fixture_path.parent.mkdir()
    monkeypatch.chdir(tmp_path)

    assert test_feature.get_test_fixture_display_name(fixture_path) == (
        "nested/fixture"
    )


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


def test_resolve_test_target_path_accepts_extensionless_pw_tests_fixture(
    monkeypatch, tmp_path
):
    tests_dir = tmp_path / "pw-tests" / "4-events"
    fixture_path = tests_dir / "32-Subscribe@Streamer.yaml"

    tests_dir.mkdir(parents = True)
    fixture_path.write_text(
        "Outbound:\n  To: any-hoster.dom\n  Subject: Echo@Domain\n",
        encoding = "utf-8",
    )

    monkeypatch.chdir(tmp_path)

    assert test_feature.resolve_test_target_path(
        "4-events/32-Subscribe@Streamer"
    ) == fixture_path


def test_test_reports_missing_fixture_instead_of_missing_keys_for_extensionless_target(
    monkeypatch, tmp_path, capsys
):
    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main(["test", "4-events/32-Subscribe@Streamer"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Test file not found: 4-events/32-Subscribe@Streamer" in captured.err
    assert "Missing PollyWeb keys" not in captured.err


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
    assert_passed_output(captured.out.strip(), fixture_path.stem)


def test_load_message_test_fixture_accepts_numeric_wait(
    tmp_path
):
    fixture_path = tmp_path / "test.yaml"
    fixture_path.write_text(
        (
            "Wait: 1.5\n"
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8",
    )

    fixture = test_feature.load_message_test_fixture(
        fixture_path,
        tmp_path / "binds.yaml",
        tmp_path / "public.pem",
    )

    assert fixture["Wait"] == 1.5


def test_load_message_test_fixture_rejects_non_numeric_wait(
    tmp_path
):
    fixture_path = tmp_path / "test.yaml"
    fixture_path.write_text(
        (
            "Wait: later\n"
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8",
    )

    with pytest.raises(test_feature.UserFacingError) as exc_info:
        test_feature.load_message_test_fixture(
            fixture_path,
            tmp_path / "binds.yaml",
            tmp_path / "public.pem",
        )

    assert str(exc_info.value) == (
        f"Test file {fixture_path} must define `Wait` as a number when present."
    )


def test_load_message_test_fixture_rejects_negative_wait(
    tmp_path
):
    fixture_path = tmp_path / "test.yaml"
    fixture_path.write_text(
        (
            "Wait: -1\n"
            "Outbound:\n"
            "  To: any-hoster.dom\n"
            "  Subject: Echo@Domain\n"
        ),
        encoding = "utf-8",
    )

    with pytest.raises(test_feature.UserFacingError) as exc_info:
        test_feature.load_message_test_fixture(
            fixture_path,
            tmp_path / "binds.yaml",
            tmp_path / "public.pem",
        )

    assert str(exc_info.value) == (
        f"Test file {fixture_path} must define `Wait` as a non-negative number."
    )


def test_run_message_test_fixture_waits_before_sending(
    monkeypatch, tmp_path
):
    sleep_calls: list[float] = []
    call_order: list[str] = []

    fixture_path = tmp_path / "test.yaml"

    def fake_load_message_test_fixture(
        path,
        binds_path,
        public_key_path
    ):
        assert path == fixture_path
        return {
            "Wait": 1.25,
            "Outbound": {
                "To": "any-hoster.dom",
                "Subject": "Echo@Domain",
            },
        }

    def fake_sleep(seconds):
        sleep_calls.append(seconds)
        call_order.append("sleep")

    def fake_send_wallet_message(**kwargs):
        call_order.append("send")
        return (
            json.dumps({"Header": {"Subject": kwargs["subject"]}}),
            None,
            "any-hoster.pollyweb.org",
        )

    monkeypatch.setattr(
        test_feature,
        "load_message_test_fixture",
        fake_load_message_test_fixture,
    )
    monkeypatch.setattr(test_feature.time, "sleep", fake_sleep)
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        fake_send_wallet_message,
    )

    output = test_feature.run_message_test_fixture(
        fixture_path,
        fixture_name = "test",
        debug = False,
        json_output = False,
        config_dir = tmp_path,
        binds_path = tmp_path / "binds.yaml",
        unsigned = False,
        anonymous = False,
        require_configured_keys = lambda: None,
        load_signing_key_pair = lambda: object(),
    )

    assert_passed_output(output, "test")
    assert sleep_calls == [1.25]
    assert call_order == ["sleep", "send"]


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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

def test_test_accepts_empty_object_as_empty_in_response(
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
            json.dumps(
                {
                    "Header": {
                        "Subject": "Echo@Domain",
                        "Algorithm": {},
                    }
                }
            ),
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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
    assert_passed_output(captured.out.strip(), test_path.stem)

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

def test_test_accepts_timestamp_wildcard_in_inbound_expectation(
    monkeypatch, tmp_path, capsys
):
    # Verify that a fixture with <timestamp> in Inbound passes when the
    # response contains a valid Zulu timestamp.
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Header:\n"
            "    Timestamp: '<timestamp>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Header":{"Timestamp":"2024-06-15T12:30:00.000Z"}}',
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)


@pytest.mark.parametrize(
    ("response_payload", "expected_message"),
    [
        (
            '{"Header":{"Timestamp":"not-a-timestamp"}}',
            "Expected response.Header.Timestamp to be a Zulu timestamp",
        ),
        (
            '{"Header":{"Timestamp":""}}',
            "Expected response.Header.Timestamp to be a Zulu timestamp",
        ),
        (
            '{"Header":{"Timestamp":12345}}',
            "Expected response.Header.Timestamp to be a timestamp string",
        ),
        (
            '{"Header":{}}',
            "Expected response.Header.Timestamp to exist in the response.",
        ),
    ],
)
def test_test_rejects_invalid_timestamp_wildcard_values(
    monkeypatch, tmp_path, capsys, response_payload, expected_message
):
    # Verify that <timestamp> rejects non-timestamps, wrong types, and missing fields.
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Header:\n"
            "    Timestamp: '<timestamp>'\n"
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


def test_test_accepts_integer_wildcard_in_inbound_expectation(
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
            "    Count: '<int>'\n"
        ),
        encoding = "utf-8")

    monkeypatch.setattr(cli, "require_configured_keys", lambda: None)
    monkeypatch.setattr(cli, "load_signing_key_pair", lambda: object())
    monkeypatch.setattr(
        test_feature,
        "send_wallet_message",
        lambda **kwargs: (
            '{"Body":{"Count":123}}',
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)


def test_test_accepts_array_template_items_alongside_exact_items(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Response:\n"
            "    Domains:\n"
            "      - Domain: any-streamer.pollyweb.org\n"
            "      - Domain: '<str>'\n"
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
                    "Response": {
                        "Domains": [
                            {"Domain": "any-subscriber.pollyweb.org"},
                            {"Domain": "any-streamer.pollyweb.org"},
                            {"Domain": "any-publisher.pollyweb.org"},
                        ]
                    }
                }
            ),
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert_passed_output(captured.out.strip(), test_path.stem)


def test_test_rejects_array_items_that_miss_the_existing_template(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Response:\n"
            "    Domains:\n"
            "      - Domain: any-streamer.pollyweb.org\n"
            "      - Domain: '<str>'\n"
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
                    "Response": {
                        "Domains": [
                            {"Domain": "any-streamer.pollyweb.org"},
                            {"Domain": ""},
                        ]
                    }
                }
            ),
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Expected response.Response.Domains[1].Domain to be a non-empty string" in captured.err


def test_test_reports_missing_fixed_array_item_without_comparing_first_item(
    monkeypatch, tmp_path, capsys
):
    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: any-hoster.pollyweb.org\n"
            "  Subject: Echo@Domain\n"
            "Inbound:\n"
            "  Response:\n"
            "    Domains:\n"
            "      - Domain: any-subscriber.pollyweb.org\n"
            "      - Domain: any-hoster.pollyweb.org\n"
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
                    "Response": {
                        "Domains": [
                            {"Domain": "any-subscriber.pollyweb.org"},
                            {"Domain": "any-streamer.pollyweb.org"},
                        ]
                    }
                }
            ),
            None,
            "any-hoster.pollyweb.org",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Expected item {'Domain': 'any-hoster.pollyweb.org'} "
        "was not found in response.Response.Domains."
    ) in captured.err
    assert "but got 'any-subscriber.pollyweb.org'" not in captured.err


@pytest.mark.parametrize(
    ("response_payload", "expected_message"),
    [
        (
            '{"Body":{"Count":"123"}}',
            "Expected response.Body.Count to be an integer",
        ),
        (
            '{"Body":{"Count":true}}',
            "Expected response.Body.Count to be an integer",
        ),
        (
            '{"Body":{}}',
            "Expected response.Body.Count to exist in the response.",
        ),
    ],
)
def test_test_rejects_invalid_integer_wildcard_values(
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
            "    Count: '<int>'\n"
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


def test_test_fails_when_response_meta_reports_server_error(
    monkeypatch, tmp_path, capsys
):
    """A wrapped server-side 500 should fail the fixture even with no HTTP error."""

    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Create@Hoster\n"
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
                    "Meta": {
                        "TotalMs": 1200,
                    },
                    "Response": {
                        "Meta": {
                            "Code": 500,
                            "Message": "Unable to create domain",
                            "Details": ["boom"],
                        },
                    },
                }
            ),
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Response returned Code 500. Unable to create domain. Details: boom" in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out


def test_test_fails_when_response_reports_top_level_server_error(
    monkeypatch, tmp_path, capsys
):
    """Keep compatibility with legacy top-level error payloads during migration."""

    test_path = tmp_path / "test.yaml"
    test_path.write_text(
        (
            "Outbound:\n"
            "  To: vault.example.com\n"
            "  Subject: Create@Hoster\n"
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
                    "Code": 500,
                    "Message": "Unable to create domain",
                    "Details": [
                        "Route53 setup failed",
                        "Certificate request failed",
                    ],
                }
            ),
            None,
            "vault.example.com",
        ))

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "Response returned Code 500. Unable to create domain." in captured.err
    assert "Route53 setup failed | Certificate request failed" in captured.err
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


def test_transport_debug_http_error_payload_keeps_embedded_message_before_error():
    """HTTP debug payloads should show an embedded inbound message first."""

    payload = transport_tools.build_debug_http_error_payload(
        json.dumps(
            {
                "error": (
                    "Legacy proxy request failed with HTTP 401: "
                    '{"Header":{"From":"any-graph.pollyweb.org","To":"client"},'
                    '"Body":{"Status":"denied"},"error":"Signature verification failed: Missing Selector"}'
                ),
                "Code": 401,
            }
        )
    )

    assert payload == {
        "Message": {
            "Header": {
                "From": "any-graph.pollyweb.org",
                "To": "client",
            },
            "Body": {
                "Status": "denied",
            },
            "error": "Signature verification failed: Missing Selector",
        },
        "Code": 401,
        "error": "Signature verification failed: Missing Selector",
    }


def test_transport_debug_http_error_payload_rewrites_backend_validation_path():
    """Backend validation paths should match the user's outbound fixture shape."""

    payload = transport_tools.build_debug_http_error_payload(
        json.dumps(
            {
                "error": (
                    "Outbound request failed: "
                    "Body.Message.Header can only contain To and Subject, got From."
                )
            }
        )
    )

    assert payload == {
        "error": (
            "Outbound request failed: "
            "Outbound.Body.Header can only contain To and Subject, got From."
        )
    }


def test_test_http_error_message_rewrites_backend_validation_path():
    """Non-debug HTTP failures should also use the outbound fixture path."""

    error = urllib.error.HTTPError(
        url = "https://pw.any-broker.pollyweb.org/inbox",
        code = 400,
        msg = "Bad Request",
        hdrs = {},
        fp = None,
    )
    setattr(
        error,
        "pollyweb_error_body",
        json.dumps(
            {
                "error": (
                    "Body.Message.Header can only contain To and Subject, got From."
                )
            }
        ),
    )

    assert test_feature.describe_http_test_error(error) == (
        "HTTP 400 Bad Request. "
        "Outbound.Body.Header can only contain To and Subject, got From."
    )


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
    assert "No DNS entry found for domain vault.example.com." in captured.err
    assert (
        "https://mxtoolbox.com/SuperTool.aspx?action="
        "a%3Apw.vault.example.com&run=toolpage"
    ) in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out


def test_test_reports_raw_dns_failures_from_wallet_send(
    monkeypatch, tmp_path, capsys
):
    """Keep leaked resolver failures on the same user-facing path."""

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
        raise socket.gaierror(8, "Name or service not known")

    monkeypatch.setattr(test_feature, "send_wallet_message", raise_dns_error)

    exit_code = cli.main(["test", str(test_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "No DNS entry found for domain vault.example.com." in captured.err
    assert (
        "https://mxtoolbox.com/SuperTool.aspx?action="
        "a%3Apw.vault.example.com&run=toolpage"
    ) in captured.err
    assert "The command failed unexpectedly" not in captured.err
    assert f"❌ Failed: {test_path.stem}" in captured.out
