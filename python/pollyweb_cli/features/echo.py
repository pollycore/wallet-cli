"""Echo feature compatibility facade and command entrypoint."""

from __future__ import annotations

from pathlib import Path

from pollyweb_cli.features import echo_presentation as _echo_presentation
from pollyweb_cli.features import echo_runtime as _echo_runtime
from pollyweb_cli.features.echo_models import ECHO_SUBJECT, _EchoCommandFailure, _EchoCommandSuccess
from pollyweb_cli.features.echo_presentation import (
    DEBUG_CONSOLE,
    ComposeResult,
    Horizontal,
    Link,
    Static,
    Vertical,
    VerticalScroll,
    _EchoTextualSection,
    _build_echo_error_footer_panel,
    _build_echo_footer_panel,
    _build_echo_header_panel,
    _build_echo_textual_sections,
    _detect_edge_provider,
    _echo_dns_context,
    _format_echo_success_metrics,
    _json_debug_renderable,
    _normalize_response_headers,
    _print_echo_dns_diagnostics,
    _print_echo_dns_reference_links,
    _print_echo_edge_details,
    _print_echo_timing_details,
    _raw_json_debug_renderable,
    _render_debug_echo_failure,
    _render_labeled_lines,
    _render_section_title,
    _should_use_textual_echo_view,
    _yaml_debug_renderable,
)
from pollyweb_cli.features.echo_response import (
    _build_echo_failure_verification_lines,
    _coerce_echo_response_metadata,
    _describe_echo_network_error,
    _extract_echo_response_metadata,
    _merge_echo_response_metadata,
    _parse_echo_response,
    _rewrite_echo_request_validation_error,
    _to_echo_user_facing_error,
)
from pollyweb_cli.features.echo_runtime import (
    _build_echo_failure_result,
    _build_textual_echo_sections,
    _initial_echo_payload_format,
    _resolve_echo_command,
)
from pollyweb_cli.tools.debug import (
    DEBUG_VALUE_STYLE,
    print_debug_json_payload,
    print_debug_payload,
    print_json_payload,
    print_labeled_value_lines,
    print_section_title,
)
from pollyweb_cli.tools.transport import send_wallet_message


class _EchoTextualApp(_echo_presentation._EchoTextualApp):
    """Compatibility wrapper that keeps widget monkeypatch hooks on `echo.py`."""

    def compose(self) -> ComposeResult:
        """Compose the reactive echo layout using this module's widget globals."""

        header_controls = Vertical(
            Link(
                "Yaml",
                url = "action://show-yaml",
                id = "toggle-yaml",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "yaml"
                    else "control-link"
                ),
            ),
            Link(
                "Json",
                url = "action://show-json",
                id = "toggle-json",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "json"
                    else "control-link"
                ),
            ),
            Link(
                "Raw",
                url = "action://show-raw",
                id = "toggle-raw",
                classes = (
                    "control-link is-active"
                    if self._payload_format == "raw"
                    else "control-link"
                ),
            ),
            id = "header-controls",
        )
        yield Horizontal(
            Static(self._header_panel, id = "header-panel"),
            header_controls,
            id = "header-bar",
        )
        yield VerticalScroll(
            *[
                Vertical(
                    Horizontal(
                        Static(
                            _render_section_title(section.title),
                            classes = "section-title",
                        ),
                        Horizontal(
                            *(
                                [
                                    Link(
                                        "Copy",
                                        url = f"action://copy/{index}",
                                        id = f"copy-{index}",
                                        classes = "copy-link",
                                    )
                                ]
                                if section.copy_text is not None
                                else []
                            ),
                            classes = "section-controls",
                        ),
                        classes = "section-bar",
                    ),
                    Static(
                        section.body,
                        classes = (
                            "section-content code-content"
                            if section.copy_text is not None
                            else "section-content"
                        ),
                    ),
                    classes = "section-block",
                )
                for index, section in enumerate(self._current_sections())
            ],
            id = "body",
        )
        yield Static(self._footer_panel, classes = "section-block")


def cmd_echo(
    domain: str,
    *,
    debug: bool,
    json_output: bool,
    config_dir,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the echo command and verify the signed response."""

    _echo_runtime.send_wallet_message = send_wallet_message

    if _should_use_textual_echo_view(debug = debug):
        with DEBUG_CONSOLE.status("Sending message..."):
            resolved = _resolve_echo_command(
                domain,
                debug = debug,
                transport_debug = False,
                json_output = json_output,
                config_dir = config_dir,
                binds_path = binds_path,
                unsigned = unsigned,
                anonymous = anonymous,
                require_configured_keys = require_configured_keys,
                load_signing_key_pair = load_signing_key_pair,
            )
            (
                yaml_sections,
                json_sections,
                raw_sections,
                footer_panel,
                exit_code,
            ) = _build_textual_echo_sections(
                resolved,
                debug = debug,
            )

        app = _EchoTextualApp(
            header_panel = _build_echo_header_panel(),
            yaml_sections = yaml_sections,
            json_sections = json_sections,
            raw_sections = raw_sections,
            footer_panel = footer_panel,
            initial_payload_format = _initial_echo_payload_format(
                json_output = json_output),
        )
        app.run()
        return exit_code

    with DEBUG_CONSOLE.status("Sending message..."):
        resolved = _resolve_echo_command(
            domain,
            debug = debug,
            transport_debug = False,
            json_output = json_output,
            config_dir = config_dir,
            binds_path = binds_path,
            unsigned = unsigned,
            anonymous = anonymous,
            require_configured_keys = require_configured_keys,
            load_signing_key_pair = load_signing_key_pair,
        )

    if isinstance(resolved, _EchoCommandFailure):
        if debug:
            _echo_presentation._print_echo_header()
        return _render_debug_echo_failure(
            domain = resolved.normalized_domain,
            debug_json = json_output,
            error_lines = resolved.error_lines,
            outbound_payload = resolved.outbound_payload,
            response_payload = resolved.response_payload,
            verification_lines = resolved.verification_lines,
            dns_diagnostics = resolved.dns_diagnostics,
            dns_link_context = resolved.dns_link_context,
            total_seconds = resolved.total_seconds,
            network_seconds = resolved.network_seconds,
            client_timeout_seconds = resolved.client_timeout_seconds,
            response_metadata = resolved.response_metadata,
            transport_metadata = resolved.transport_metadata,
            header_panel = _build_echo_header_panel(),
        )

    if not debug:
        if json_output:
            print_json_payload(resolved.parsed_response_payload)
            return 0

        print(
            _format_echo_success_metrics(
                total_seconds = resolved.total_seconds,
                network_seconds = resolved.network_seconds,
                response_metadata = resolved.response_metadata)
        )
        return 0

    _echo_presentation._print_echo_header()

    debug_payload_printer = print_debug_json_payload if json_output else print_debug_payload
    if resolved.outbound_payload is not None:
        debug_payload_printer(
            f"Outbound payload to https://pw.{resolved.normalized_domain}/inbox",
            resolved.outbound_payload,
        )
    debug_payload_printer(
        "Inbound payload",
        resolved.parsed_response_payload,
    )

    print_section_title(f"Verified echo response from {domain}")
    print_labeled_value_lines(
        resolved.verification_lines,
        prefix = " - ",
    )
    _print_echo_dns_diagnostics(
        resolved.dns_diagnostics,
        json_output = json_output)
    if resolved.dns_link_context is not None:
        _print_echo_dns_reference_links(*resolved.dns_link_context)
    _print_echo_timing_details(
        total_seconds = resolved.total_seconds,
        network_seconds = resolved.network_seconds,
        response_metadata = resolved.response_metadata,
        client_timeout_seconds = resolved.client_timeout_seconds)
    _print_echo_edge_details(resolved.transport_metadata)
    print()
    if resolved.footer_panel is not None:
        DEBUG_CONSOLE.print(resolved.footer_panel)
    print()
    return 0
