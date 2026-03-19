from __future__ import annotations

from rich.syntax import Syntax

from pollyweb_cli.tools import debug as debug_tools


def test_build_json_syntax_uses_pretty_indented_json():
    renderable = debug_tools.build_json_syntax({"outer": {"inner": True}})

    assert renderable.code == '{\n  "outer": {\n    "inner": true\n  }\n}'


def test_render_debug_yaml_adds_code_block_background():
    renderable = debug_tools.render_debug_yaml("Header:\n  Subject: Echo@Domain")

    assert any(
        span.style == debug_tools.DEBUG_CODE_BACKGROUND_STYLE
        for span in renderable.spans
    )


def test_print_json_payload_uses_rich_syntax_for_interactive_terminals(
    monkeypatch
):
    printed: list[tuple[object, object]] = []

    monkeypatch.setattr(debug_tools, "_should_colorize_json_output", lambda: True)
    monkeypatch.setattr(
        debug_tools.DEBUG_CONSOLE,
        "print",
        lambda payload, overflow = None: printed.append((payload, overflow)),
    )

    debug_tools.print_json_payload({"ok": True})

    assert len(printed) == 1
    assert isinstance(printed[0][0], Syntax)
    assert printed[0][1] == "fold"


def test_print_json_payload_keeps_plain_json_for_non_interactive_output(
    monkeypatch,
    capsys
):
    monkeypatch.setattr(debug_tools, "_should_colorize_json_output", lambda: False)

    debug_tools.print_json_payload({"ok": True})

    captured = capsys.readouterr()
    assert captured.out == '{"ok":true}\n'
