from __future__ import annotations

import builtins
import json
import socket
import stat
import sys
import time
import uuid
import urllib.error
from pathlib import Path

import pollyweb._transport as pollyweb_transport
import pollyweb.msg as pollyweb_msg
import pytest
from rich.console import Group
from rich.syntax import Syntax
from rich.text import Text

from pollyweb import DnsQueryDiagnostic, DnsVerificationDiagnostics, Msg
from pollyweb_cli import cli
from pollyweb_cli.features import chat as chat_feature
from pollyweb_cli.features import echo as echo_feature
from pollyweb_cli.features import test as test_feature

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


def _fake_dns_diagnostics(
    domain: str = "vault.example.com",
    selector: str = "default"
):
    """Build stable DNS diagnostics for echo debug output tests."""

    return DnsVerificationDiagnostics(
        Domain = domain,
        PollyWebBranch = f"pw.{domain}",
        Selector = selector,
        DkimName = f"{selector}._domainkey.pw.{domain}",
        DnssecRequested = True,
        Nameservers = ["1.1.1.1"],
        Queries = [
            DnsQueryDiagnostic(
                Name = f"pw.{domain}",
                Type = "DS",
                ResponseCode = "NOERROR",
                AuthenticData = True,
                Answers = ["12345 13 2 ABCDEF"],
            ),
            DnsQueryDiagnostic(
                Name = f"{selector}._domainkey.pw.{domain}",
                Type = "TXT",
                ResponseCode = "NOERROR",
                AuthenticData = True,
                Answers = ["v=DKIM1; k=ed25519; p=PUBLICKEY"],
            ),
        ],
    )


def test_echo_sends_signed_message_and_verifies_response(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert payload["Header"]["To"] == "vault.example.com"
        assert payload["Header"]["Subject"] == "Echo@Domain"
        assert payload["Header"]["From"] == "Anonymous"

        # Reply From: vault.example.com To: vault.example.com
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    perf_counter_values = iter([100.0, 100.10, 100.22, 100.42])
    monkeypatch.setattr(
        time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out == "✅ Verified echo response (420 ms, 29% latency)\n"
    assert captured.err == ""

def test_echo_fails_when_signature_does_not_verify(monkeypatch, tmp_path, capsys):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    wrong_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            wrong_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "did not verify" in captured.err
    assert "Invalid signature" in captured.err

def test_echo_fails_when_response_headers_do_not_make_sense(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="other.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "unexpected From value: other.example.com" in captured.err

def test_echo_debug_prints_outbound_and_inbound_payloads(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value="vault.example.com",
                correlation=payload["Header"]["Correlation"],
                private_key=remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "pw echo v" in captured.out or "PollyWeb CLI v" in captured.out
    assert "vault.example.com" in captured.out
    assert "Echo summary" in captured.out
    assert "✅ DKIM and DNSSEC" in captured.out
    assert "✅ Signed message" in captured.out
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "To: vault.example.com" in captured.out
    assert "From: Anonymous" in captured.out.split("\n\nInbound payload:\n", 1)[0]
    assert "\n\nInbound payload:\n" in captured.out
    assert captured.out.count("\n\nInbound payload:\n") == 1
    assert "From: vault.example.com" in captured.out
    assert "Echo: ok" in captured.out
    assert "\nDNS verification diagnostics:\n" in captured.out
    assert "PollyWebBranch: pw.vault.example.com" in captured.out
    assert "DkimName: default._domainkey.pw.vault.example.com" in captured.out
    assert "DnssecRequested: true" in captured.out
    assert "AuthenticData: true" in captured.out
    assert "External DNS checks:" in captured.out
    assert "MXToolbox DKIM test:" in captured.out
    assert "DNSSEC Debugger test:" in captured.out
    assert "Google DNS test:" in captured.out
    assert "Google DNS A record test:" in captured.out
    assert "mxtoolbox.com/SuperTool.aspx?action=dkim%3Apw.vault.example.com%3Adefault&run=toolpage" in captured.out
    assert "dnssec-debugger.verisignlabs.com/pw.vault.example.com" in captured.out
    assert "dns.google/query?name=pw.vault.example.com" in captured.out
    assert "dns.google/resolve?name=pw.vault.example.com&type=A" in captured.out
    assert "Verified echo response from vault.example.com:" in captured.out
    assert " - Schema validated: pollyweb.org/MSG:1.0" in captured.out
    assert " - Required signed headers: were present" in captured.out
    assert " - Canonical payload hash: matched the signed content" in captured.out
    assert (
        " - Signature verified: via DKIM lookup for selector default "
        "on vault.example.com" in captured.out
    )
    assert " - From matched expected domain: vault.example.com" in captured.out
    assert " - To matched expected sender: vault.example.com" in captured.out
    assert " - Subject matched expected echo subject: Echo@Domain" in captured.out
    assert "\nNetwork timing:\n" in captured.out
    assert " - Total duration:" in captured.out
    assert " - Latency share: " in captured.out
    assert "\nEdge / CDN hints:\n" in captured.out
    assert " - Transport headers: unavailable in this runtime" in captured.out
    assert captured.err == ""


def test_echo_json_prints_raw_response_payload(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "--json", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["Header"]["Subject"] == "Echo@Domain"
    assert parsed["Header"]["From"] == "vault.example.com"
    assert parsed["Body"]["Echo"] == "ok"
    assert "Verified echo response" not in captured.out
    assert captured.err == ""


def test_echo_yaml_debug_renderable_keeps_literal_strings_yaml_safe():
    renderable = echo_feature._yaml_debug_renderable(
        {
            "Hash": "a" * 80,
            "Signature": "b" * 80,
        }
    )

    rendered = renderable.plain

    assert "!!python/object" not in rendered
    assert "Hash: |" in rendered
    assert "Signature: |" in rendered


def test_echo_textual_app_keeps_rich_static_sections():
    created_static_widgets: list[object] = []

    class FakeStatic:
        """Capture the renderables sent into Textual static widgets."""

        def __init__(self, renderable, *, classes = None, id = None, **_kwargs):
            self.renderable = renderable
            self.classes = classes
            self.id = id
            created_static_widgets.append(self)

    class FakeVerticalScroll:
        """Minimal context manager stand-in for the Textual body container."""

        def __init__(self, *children, id = None, classes = None, **_kwargs):
            self.children = list(children)
            self.id = id
            self.classes = classes

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    original_static = echo_feature.Static
    original_horizontal = echo_feature.Horizontal
    original_vertical = echo_feature.Vertical
    original_link = echo_feature.Link
    original_vertical_scroll = echo_feature.VerticalScroll
    echo_feature.Static = FakeStatic
    echo_feature.Horizontal = FakeVerticalScroll
    echo_feature.Vertical = FakeVerticalScroll
    echo_feature.Link = FakeStatic
    echo_feature.VerticalScroll = FakeVerticalScroll

    try:
        app = echo_feature._EchoTextualApp(
            header_panel = echo_feature._build_echo_header_panel(),
            yaml_sections = [
                echo_feature._EchoTextualSection(
                    title = "Verified response",
                    body = Text("copy me", style = echo_feature.DEBUG_VALUE_STYLE),
                    copy_text = "copy me",
                )
            ],
            json_sections = [
                echo_feature._EchoTextualSection(
                    title = "Verified response",
                    body = Text("copy json", style = echo_feature.DEBUG_VALUE_STYLE),
                    copy_text = "copy json",
                )
            ],
            raw_sections = [
                echo_feature._EchoTextualSection(
                    title = "Verified response",
                    body = Text("copy raw", style = echo_feature.DEBUG_VALUE_STYLE),
                    copy_text = "copy raw",
                )
            ],
            footer_panel = echo_feature._build_echo_footer_panel(
                total_seconds = 0.2,
                network_seconds = 0.1,
                dkim_and_dnssec_verified = True,
                cdn_distribution_detected = True,
            ),
            initial_payload_format = "yaml",
        )

        composed = list(app.compose())
    finally:
        echo_feature.Static = original_static
        echo_feature.Horizontal = original_horizontal
        echo_feature.Vertical = original_vertical
        echo_feature.Link = original_link
        echo_feature.VerticalScroll = original_vertical_scroll

    assert len(composed) == 3
    assert len(created_static_widgets) >= 4
    assert any(
        getattr(widget.renderable, "plain", None) == "Verified response:"
        for widget in created_static_widgets
    )
    assert len(composed[1].children) == 1


def test_echo_textual_app_toggle_switches_payload_sections():
    app = echo_feature._EchoTextualApp(
        header_panel = echo_feature._build_echo_header_panel(),
        yaml_sections = [
            echo_feature._EchoTextualSection(
                title = "YAML section",
                body = Text("yaml body", style = echo_feature.DEBUG_VALUE_STYLE),
            )
        ],
        json_sections = [
            echo_feature._EchoTextualSection(
                title = "JSON section",
                body = Text("json body", style = echo_feature.DEBUG_VALUE_STYLE),
            )
        ],
        raw_sections = [
            echo_feature._EchoTextualSection(
                title = "Raw section",
                body = Text("raw body", style = echo_feature.DEBUG_VALUE_STYLE),
            )
        ],
        footer_panel = echo_feature._build_echo_footer_panel(
            total_seconds = 0.2,
            network_seconds = 0.1,
            dkim_and_dnssec_verified = True,
            cdn_distribution_detected = True,
        ),
        initial_payload_format = "yaml",
    )

    assert app._current_sections()[0].title == "YAML section"


def test_echo_textual_app_routes_link_actions_to_toggles_and_copy():
    app = echo_feature._EchoTextualApp(
        header_panel = echo_feature._build_echo_header_panel(),
        yaml_sections = [
            echo_feature._EchoTextualSection(
                title = "YAML section",
                body = Text("yaml body", style = echo_feature.DEBUG_VALUE_STYLE),
                copy_text = "yaml copy",
            )
        ],
        json_sections = [
            echo_feature._EchoTextualSection(
                title = "JSON section",
                body = Text("json body", style = echo_feature.DEBUG_VALUE_STYLE),
                copy_text = "json copy",
            )
        ],
        raw_sections = [
            echo_feature._EchoTextualSection(
                title = "Raw section",
                body = Text("raw body", style = echo_feature.DEBUG_VALUE_STYLE),
                copy_text = "raw copy",
            )
        ],
        footer_panel = echo_feature._build_echo_footer_panel(
            total_seconds = 0.2,
            network_seconds = 0.1,
            dkim_and_dnssec_verified = True,
            cdn_distribution_detected = True,
        ),
        initial_payload_format = "yaml",
    )
    copied = []
    timer_callbacks = []

    class FakeTimer:
        """Capture one-shot timer resets without requiring a live app loop."""

        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    app.copy_to_clipboard = copied.append
    app.set_timer = lambda _delay, callback, **_kwargs: (timer_callbacks.append(callback), FakeTimer())[1]

    app.open_url("action://show-json")
    assert app._current_sections()[0].title == "JSON section"

    app.open_url("action://copy/0")
    assert copied == ["json copy"]
    assert app._copied_section == ("json", 0)
    assert len(timer_callbacks) == 1

    timer_callbacks.pop()()
    assert app._copied_section is None

    app.open_url("action://show-yaml")
    assert app._current_sections()[0].title == "YAML section"

    app.open_url("action://show-raw")
    assert app._current_sections()[0].title == "Raw section"

    app.open_url("action://copy/0")
    assert copied == ["json copy", "raw copy"]
    assert app._copied_section == ("raw", 0)

    app.action_show_json()

    assert app._current_sections()[0].title == "JSON section"

    app.action_show_yaml()

    assert app._current_sections()[0].title == "YAML section"


def test_echo_textual_sections_mark_payload_blocks_as_copyable():
    sections = echo_feature._build_echo_textual_sections(
        domain = "vault.example.com",
        debug = True,
        payload_format = "json",
        outbound_payload = {"Header": {"Subject": "Echo@Domain"}},
        response_payload = '{"Header":{"Subject":"Echo@Domain"},"Body":{"Echo":"ok"}}',
        dns_diagnostics = None,
        dns_link_context = None,
        verification_lines = {"Schema validated": "pollyweb.org/MSG:1.0"},
        total_seconds = 0.1,
        network_seconds = 0.05,
        response_metadata = None,
        transport_metadata = {},
    )

    assert sections[0].copy_text is not None
    assert sections[1].copy_text is not None
    assert sections[2].copy_text is None


def test_echo_json_textual_renderable_uses_syntax_highlighting():
    renderable = echo_feature._json_debug_renderable({"ok": True})

    assert isinstance(renderable, Syntax)


def test_echo_json_textual_renderable_uses_pretty_indentation():
    renderable = echo_feature._json_debug_renderable({"outer": {"inner": True}})

    assert renderable.code == '{\n  "outer": {\n    "inner": true\n  }\n}'


def test_echo_raw_json_textual_renderable_uses_compact_json():
    renderable = echo_feature._raw_json_debug_renderable({"outer": {"inner": True}})

    assert renderable.plain == '{"outer":{"inner":true}}'


def test_echo_debug_prints_outbound_and_inbound_payloads_for_dom_alias(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        assert request.full_url == "https://pw.any-domain.pollyweb.org/inbox"
        assert payload["Header"]["To"] == "any-domain.pollyweb.org"
        assert payload["Header"]["From"] == "Anonymous"
        assert "Hash" not in payload
        assert "Signature" not in payload
        return DummyResponse(
            make_echo_response_payload(
                from_value = "any-domain.pollyweb.org",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "--debug", "any-domain.dom"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "pw echo v" in captured.out or "PollyWeb CLI v" in captured.out
    assert "any-domain.dom" in captured.out or "any-domain.pollyweb.org" in captured.out
    assert "Echo summary" in captured.out
    assert "Echo summary" in captured.out
    assert "✅ DKIM and DNSSEC" in captured.out
    assert "✅ Signed message" in captured.out
    assert (
        "\nOutbound payload to https://pw.any-domain.pollyweb.org/inbox:\n"
        in captured.out
    )
    assert "Subject: Echo@Domain" in captured.out
    assert "To: any-domain.pollyweb.org" in captured.out
    outbound = captured.out.split("\n\nInbound payload:\n", 1)[0]
    assert "From: Anonymous" in outbound
    assert "Hash:" not in outbound
    assert "Signature:" not in outbound
    assert "\n\nInbound payload:\n" in captured.out
    assert captured.out.count("\n\nInbound payload:\n") == 1
    assert "From: any-domain.pollyweb.org" in captured.out
    assert "Echo: ok" in captured.out
    assert "\nDNS verification diagnostics:\n" in captured.out
    assert "PollyWebBranch: pw.any-domain.pollyweb.org" in captured.out
    assert "MXToolbox DKIM test:" in captured.out
    assert "DNSSEC Debugger test:" in captured.out
    assert "Google DNS test:" in captured.out
    assert "Google DNS A record test:" in captured.out
    assert "mxtoolbox.com/SuperTool.aspx?action=dkim%3Apw.any-domain.pollyweb.org%3Adefault&run=toolpage" in captured.out
    assert "dns.google/query?name=pw.any-domain.pollyweb.org" in captured.out
    assert "dns.google/resolve?name=pw.any-domain.pollyweb.org&type=A" in captured.out
    assert "Verified echo response from any-domain.dom:" in captured.out
    assert (
        " - Signature verified: via DKIM lookup for selector default "
        "on any-domain.pollyweb.org" in captured.out
    )
    assert " - From matched expected domain: any-domain.pollyweb.org" in captured.out
    assert " - To matched expected sender: any-domain.pollyweb.org" in captured.out
    assert "\nNetwork timing:\n" in captured.out
    assert "\nEdge / CDN hints:\n" in captured.out
    assert captured.err == ""


def test_echo_debug_json_switches_payload_sections_to_raw_json(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "--debug", "--json", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "pw echo v" in captured.out or "PollyWeb CLI v" in captured.out
    assert "\nOutbound payload to https://pw.vault.example.com/inbox:\n" in captured.out
    assert '"Subject":"Echo@Domain"' in captured.out
    assert '"To":"vault.example.com"' in captured.out
    assert "\n\nInbound payload:\n" in captured.out
    assert '"Echo":"ok"' in captured.out
    assert "\nDNS verification diagnostics:\n" in captured.out
    assert '"PollyWebBranch":"pw.vault.example.com"' in captured.out
    assert "Subject: Echo@Domain" not in captured.out
    assert "PollyWebBranch: pw.vault.example.com" not in captured.out
    assert "Echo summary" in captured.out
    assert captured.err == ""


def test_echo_debug_prints_cloudfront_edge_hints_when_transport_headers_are_available(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    request_message = Msg(
        To = "vault.example.com",
        Subject = "Echo@Domain",
        Correlation = "123e4567-e89b-12d3-a456-426614174000",
        Body = {},
    )
    response_payload = make_echo_response_payload(
        from_value = "vault.example.com",
        correlation = request_message.Correlation,
        private_key = remote_key_pair.PrivateKey,
    ).decode("utf-8")

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        echo_feature,
        "send_wallet_message",
        lambda **kwargs: (
            kwargs["timing"].update({"network_seconds": 0.33}),
            kwargs["transport_metadata"].update(
                {
                    "http_status": 200,
                    "http_reason": "OK",
                    "request_url": "https://pw.vault.example.com/inbox",
                    "response_headers": {
                        "server": "CloudFront",
                        "via": "1.1 123abc.cloudfront.net (CloudFront)",
                        "x-cache": "Miss from cloudfront",
                        "x-amz-cf-pop": "LIS50-P1",
                        "x-amz-cf-id": "cloudfront-request-id",
                    },
                }
            ),
            (response_payload, request_message, "vault.example.com"),
        )[-1],
    )
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )
    perf_counter_values = iter([50.0, 50.4])
    monkeypatch.setattr(
        time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    exit_code = cli.main(["echo", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nEdge / CDN hints:\n" in captured.out
    assert " - Request URL: https://pw.vault.example.com/inbox" in captured.out
    assert " - HTTP status: 200 OK" in captured.out
    assert " - Edge provider: CloudFront" in captured.out
    assert " - Edge PoP: LIS50-P1" in captured.out
    assert " - Server header: CloudFront" in captured.out
    assert " - Via header: 1.1 123abc.cloudfront.net (CloudFront)" in captured.out
    assert " - X-Cache: Miss from cloudfront" in captured.out
    assert " - CloudFront request ID: cloudfront-request-id" in captured.out


def test_echo_debug_prints_metadata_performance_metrics_in_network_timing(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
                body = {
                    "Echo": "ok",
                    "Metadata": {
                        "TotalExecutionMs": 8,
                        "DownstreamExecutionMs": 0,
                    },
                },
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )
    perf_counter_values = iter([10.0, 10.04, 10.08, 10.12])
    monkeypatch.setattr(
        time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )

    exit_code = cli.main(["echo", "--debug", "vault.example.com"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "\nNetwork timing:\n" in captured.out
    assert " - Total duration: 120 ms" in captured.out
    assert " - Latency share: 33% (40 ms)" in captured.out
    assert " - Total execution: 8 ms" in captured.out
    assert " - Downstream execution: 0 ms" in captured.out
    assert captured.err == ""


def test_echo_debug_rejects_unexpected_top_level_response_fields(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    request_message = Msg(
        To = "any-domain.pollyweb.org",
        Subject = "Echo@Domain",
        Correlation = "123e4567-e89b-12d3-a456-426614174000",
        Body = {},
    )
    response_payload = cli.json.dumps(
        {
            "Body": {"Echo": "ok"},
            "Header": {
                "Algorithm": "ed25519-sha256",
                "Correlation": request_message.Correlation,
                "From": "any-domain.pollyweb.org",
                "Schema": "pollyweb.org/MSG:1.0",
                "Selector": "default",
                "Subject": "Echo@Domain",
                "Timestamp": "2026-03-18T16:18:38.411Z",
                "To": "any-domain.pollyweb.org",
            },
            "Hash": "fb79347b8a1117f5a74eae029be8629e7e6d8286c0e3020a08641d0e512add49",
            "Request": {
                "Body": {},
                "Header": {
                    "From": "Anonymous",
                },
            },
            "Signature": (
                "78QEPU+LdK1Fxu0DdXJLlh/pcWs024KkJ3ToCOFpk+KddEfebVh6xK9rmzvoLVS1"
                "qxmagMETICfnYiZA/IZECg=="
            ),
        }
    )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        echo_feature,
        "send_wallet_message",
        lambda **kwargs: (
            response_payload,
            request_message,
            "any-domain.pollyweb.org",
        ),
    )
    exit_code = cli.main(["echo", "--debug", "any-domain.dom"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "\nError summary:\n" in captured.out
    assert " - Status: failed" in captured.out
    assert (
        " - Error: Echo response from any-domain.pollyweb.org had unexpected "
        "top-level field(s): Request. Expected only Body, Hash, Header, and "
        "Signature." in captured.out
    )
    assert " - Error type: UserFacingError" in captured.out
    assert "\nDNS verification diagnostics:\n" not in captured.out
    assert "External DNS checks:" in captured.out
    assert "\nEcho response:\n" not in captured.out
    assert captured.err == ""


def test_echo_debug_prints_dns_diagnostics_on_verification_failure(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    wrong_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
                selector = "pw1",
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            wrong_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "--debug", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "\nError summary:\n" in captured.out
    assert " - Status: failed" in captured.out
    assert "did not verify" in captured.out
    assert " - Error type: UserFacingError" in captured.out
    assert "\nDNS verification diagnostics:\n" in captured.out
    assert "Selector: pw1" in captured.out
    assert "DkimName: pw1._domainkey.pw.vault.example.com" in captured.out
    assert "dnssec-debugger.verisignlabs.com/pw.vault.example.com" in captured.out
    assert captured.err == ""


def test_echo_accepts_response_to_stored_bind(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": VALID_WALLET_ID,
                    "Domain": "any-hoster.pollyweb.org",
                }
            ]
        ),
        encoding = "utf-8",
    )

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "any-hoster.pollyweb.org",
                to_value = VALID_WALLET_ID,
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    perf_counter_values = iter([10.0, 10.02, 10.07, 10.2])
    monkeypatch.setattr(
        time,
        "perf_counter",
        lambda: next(perf_counter_values),
    )
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "any-hoster.pollyweb.org"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "✅ Verified echo response (200 ms, 25% latency)" in captured.out
    assert captured.err == ""


def test_echo_rejects_unrelated_response_to_value(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    binds_path = config_dir / "binds.yaml"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    remote_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())
    binds_path.write_text(
        cli.yaml.safe_dump(
            [
                {
                    "Bind": VALID_WALLET_ID,
                    "Domain": "vault.example.com",
                }
            ]
        ),
        encoding = "utf-8",
    )

    def fake_urlopen(request):
        payload = cli.json.loads(request.data.decode("utf-8"))
        return DummyResponse(
            make_echo_response_payload(
                from_value = "vault.example.com",
                to_value = "30ddc4c7-ba23-4bae-971c-2595143f69eb",
                correlation = payload["Header"]["Correlation"],
                private_key = remote_key_pair.PrivateKey,
            )
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli, "BINDS_PATH", binds_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        pollyweb_msg,
        "_resolve_dkim_public_key",
        lambda domain, selector: (
            remote_key_pair.PublicKey,
            "ed25519",
            _fake_dns_diagnostics(domain, selector),
        ),
    )

    exit_code = cli.main(["echo", "vault.example.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "unexpected To value: 30ddc4c7-ba23-4bae-971c-2595143f69eb"
        in captured.err
    )


def test_echo_reports_human_readable_dns_failures(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(_request):
        raise urllib.error.URLError(
            socket.gaierror(8, "nodename nor servname provided, or not known")
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["echo", "any-non-existing.dom"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Echo request to any-non-existing.dom failed: "
        "Could not resolve PollyWeb inbox host "
        "pw.any-non-existing.pollyweb.org."
        " Check that the domain name is correct and that its DNS record exists."
    ) in captured.err
    assert "gaierror(" not in captured.err


def test_echo_debug_keeps_raw_dns_failure_details(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    def fake_urlopen(_request):
        raise urllib.error.URLError(
            socket.gaierror(8, "nodename nor servname provided, or not known")
        )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)

    exit_code = cli.main(["echo", "--debug", "non-existing-domain.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Echo request to non-existing-domain.com failed: "
        "gaierror(8, 'nodename nor servname provided, or not known')"
    ) in captured.err
    assert "Could not resolve PollyWeb inbox host" not in captured.err


def test_echo_debug_shows_in_app_summary_for_request_validation_errors(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        echo_feature,
        "send_wallet_message",
        lambda **_kwargs: (_ for _ in ()).throw(
            pollyweb_msg.MsgValidationError("To must be a domain string or a UUID")
        ),
    )

    exit_code = cli.main(["echo", "--debug", "any-domain"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "pw echo v" in captured.out
    assert "\nError summary:\n" in captured.out
    assert " - Status: failed" in captured.out
    assert " - Error type: MsgValidationError" in captured.out
    assert " - Stage: request construction" in captured.out
    assert " - Error: To must be a domain string." in captured.out
    assert "Echo summary" in captured.out
    assert "❌ Echo request failed" in captured.out
    assert "Traceback" not in captured.out
    assert captured.err == ""


def test_echo_reports_domain_only_request_validation_errors(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        echo_feature,
        "send_wallet_message",
        lambda **_kwargs: (_ for _ in ()).throw(
            pollyweb_msg.MsgValidationError("To must be a domain string or a UUID")
        ),
    )

    exit_code = cli.main(["echo", "123e4567-e89b-12d3-a456-426614174000"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "Error: Echo request to 123e4567-e89b-12d3-a456-426614174000 failed: "
        "To must be a domain string."
    ) in captured.err


def test_echo_reports_human_readable_dns_failures_from_custom_transport(
    monkeypatch, tmp_path, capsys
):
    config_dir = tmp_path / ".pollyweb"
    private_key_path = config_dir / "private.pem"
    public_key_path = config_dir / "public.pem"
    config_dir.mkdir()
    local_key_pair = cli.KeyPair()
    private_key_path.write_bytes(local_key_pair.private_pem_bytes())
    public_key_path.write_bytes(local_key_pair.public_pem_bytes())

    class FailingConnection:
        """Simulate a resolver failure inside the custom HTTPS transport."""

        def request(
            self,
            _method,
            _path,
            *,
            body = None,
            headers = None
        ):
            raise socket.gaierror(
                8,
                "nodename nor servname provided, or not known",
            )

    monkeypatch.setattr(cli, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(cli, "PRIVATE_KEY_PATH", private_key_path)
    monkeypatch.setattr(cli, "PUBLIC_KEY_PATH", public_key_path)
    monkeypatch.setattr(
        pollyweb_transport._HTTPS_CONNECTION_POOL,
        "_get_connection",
        lambda host, port, timeout = 10.0: FailingConnection(),
    )
    monkeypatch.setattr(
        pollyweb_transport._HTTPS_CONNECTION_POOL,
        "_drop_connection",
        lambda host, port: None,
    )

    exit_code = cli.main(["echo", "non-existing-domain.com"])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert (
        "Echo request to non-existing-domain.com failed: "
        "Could not resolve PollyWeb inbox host pw.non-existing-domain.com."
        " Check that the domain name is correct and that its DNS record exists."
    ) in captured.err
    assert "Traceback" not in captured.err

def test_print_echo_response_formats_payload(capsys):
    cli.print_echo_response(
        '{"Header":{"Subject":"Echo@Domain"},"Body":{"Echo":"ok"}}'
    )

    captured = capsys.readouterr()
    assert "\nEcho response:\n" in captured.out
    assert "Subject: Echo@Domain" in captured.out
    assert "Echo: ok" in captured.out
