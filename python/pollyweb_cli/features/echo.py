"""Echo feature verification and command implementation."""

from __future__ import annotations

import json
import time
import urllib.error
from pathlib import Path

from pollyweb import Msg, MsgValidationError
from textual.app import ComposeResult

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    describe_bind_network_error,
    get_first_bind_for_domain,
    load_binds,
)
from pollyweb_cli.features import echo_presentation as _echo_presentation
from pollyweb_cli.features.echo_presentation import (
    Horizontal,
    Link,
    Static,
    Vertical,
    VerticalScroll,
    _EchoTextualSection,
    _build_echo_error_footer_panel,
    _build_echo_error_textual_sections,
    _build_echo_footer_panel,
    _build_echo_header_panel,
    _build_echo_textual_sections,
    _detect_edge_provider,
    _echo_dns_context,
    _format_echo_success_metrics,
    _json_debug_copy_text,
    _json_debug_renderable,
    _normalize_response_headers,
    _print_echo_dns_diagnostics,
    _print_echo_dns_reference_links,
    _print_echo_edge_details,
    _print_echo_header,
    _print_echo_timing_details,
    _render_debug_echo_failure,
    _render_section_title,
    _render_labeled_lines,
    _should_use_textual_echo_view,
    _yaml_debug_renderable,
)
from pollyweb_cli.tools.debug import (
    DEBUG_CONSOLE,
    DEBUG_VALUE_STYLE,
    parse_debug_payload,
    print_json_payload,
    print_labeled_value_lines,
    print_section_title,
)
from pollyweb_cli.tools.transport import build_debug_outbound_payload, build_wallet_sender
from pollyweb_cli.tools.transport import send_wallet_message


ECHO_SUBJECT = "Echo@Domain"
ALLOWED_ECHO_RESPONSE_FIELDS = frozenset({"Body", "Hash", "Header", "Signature"})


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
            id = "header-controls",
        )
        header_controls.border_title = "View"

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


def _coerce_echo_response_metadata(
    metadata: object
) -> dict[str, object] | None:
    """Return echo response metadata as a plain mapping when available."""

    if isinstance(metadata, dict):
        return metadata

    if hasattr(metadata, "get"):
        coerced: dict[str, object] = {}
        found_value = False

        for key in ("TotalExecutionMs", "DownstreamExecutionMs"):
            value = metadata.get(key)
            if value is not None:
                coerced[key] = value
                found_value = True

        if found_value:
            return coerced

    return None


def _to_echo_user_facing_error(
    exc: MsgValidationError,
    *,
    domain: str
) -> UserFacingError:
    """Translate library verification failures into echo-specific CLI wording."""

    message = str(exc)
    diagnostics = getattr(exc, "dns_diagnostics", None)

    if message.startswith("Unexpected top-level field(s):"):
        lowered_message = message[0].lower() + message[1:]
        return UserFacingError(
            f"Echo response from {domain} had {lowered_message}",
            diagnostics = diagnostics)

    if message.startswith("Unexpected "):
        return UserFacingError(
            f"Echo response from {domain} had an {message[0].lower() + message[1:]}",
            diagnostics = diagnostics)

    return UserFacingError(
        f"Echo response from {domain} did not verify: {message}",
        diagnostics = diagnostics)


def _rewrite_echo_request_validation_error(
    exc: MsgValidationError
) -> str:
    """Return echo-specific wording for request-construction validation errors."""

    message = str(exc)

    if message == "To must be a domain string or a UUID":
        return "To must be a domain string."

    return message


def _describe_echo_network_error(
    domain: str,
    reason: object,
    *,
    debug: bool
) -> str:
    """Format echo transport failures for either normal or debug output."""

    if debug:
        if isinstance(reason, str):
            return reason

        return repr(reason)

    return describe_bind_network_error(
        domain,
        reason)


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

    dns_diagnostics = None
    dns_link_context: tuple[str, str] | None = None
    timing: dict[str, float] = {}
    transport_metadata: dict[str, object] = {}
    started_at = time.perf_counter()
    normalized_domain = domain
    response_payload: str | None = None
    request_message = None
    response_metadata: object | None = None

    if debug:
        _print_echo_header()

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        response_payload, request_message, normalized_domain = send_wallet_message(
            domain = domain,
            subject = ECHO_SUBJECT,
            body = {},
            key_pair = key_pair,
            debug = debug,
            debug_json = json_output,
            binds_path = binds_path,
            anonymous = anonymous,
            unsigned = unsigned,
            timing = timing,
            transport_metadata = transport_metadata,
        )
        if debug:
            dns_link_context = _echo_dns_context(
                response_payload,
                fallback_domain = normalized_domain)
        allowed_to = {normalized_domain}

        stored_bind = get_first_bind_for_domain(
            normalized_domain,
            load_binds(binds_path))
        if stored_bind is not None:
            allowed_to.add(stored_bind)

        try:
            response = Msg.parse(
                response_payload,
                allowed_top_level_fields = ALLOWED_ECHO_RESPONSE_FIELDS)
        except MsgValidationError as exc:
            raise _to_echo_user_facing_error(
                exc,
                domain = normalized_domain) from None
        except Exception as exc:
            raise UserFacingError(
                f"Could not parse the echo response from {normalized_domain}: {exc}"
            ) from None

        try:
            verification = response.verify_details(
                expected_from = normalized_domain,
                expected_subject = ECHO_SUBJECT,
                expected_correlation = request_message.Correlation,
                allowed_to_values = allowed_to)
        except MsgValidationError as exc:
            raise _to_echo_user_facing_error(
                exc,
                domain = normalized_domain) from None

        if hasattr(response.Body, "get"):
            response_metadata = _coerce_echo_response_metadata(
                response.Body.get("Metadata")
            )

        dns_diagnostics = verification.dns_diagnostics
    except UserFacingError as exc:
        dns_diagnostics = getattr(exc, "diagnostics", dns_diagnostics)
        if debug:
            outbound_payload = None
            if request_message is not None:
                wallet, _ = build_wallet_sender(
                    normalized_domain,
                    key_pair,
                    binds_path = binds_path,
                    anonymous = anonymous,
                )
                outbound_payload = build_debug_outbound_payload(
                    wallet,
                    request_message,
                    unsigned = unsigned,
                )

            return _render_debug_echo_failure(
                domain = normalized_domain,
                debug_json = json_output,
                error_lines = {
                    "Status": "failed",
                    "Error": str(exc),
                    "Error type": exc.__class__.__name__,
                },
                outbound_payload = outbound_payload,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                total_seconds = time.perf_counter() - started_at,
                network_seconds = timing.get("network_seconds", 0.0),
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            )
        raise
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Echo request to {domain} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = _describe_echo_network_error(
            domain,
            exc.reason,
            debug = debug)
        raise UserFacingError(
            f"Echo request to {domain} failed: {reason}"
        ) from None
    except MsgValidationError as exc:
        request_error = _rewrite_echo_request_validation_error(exc)

        if not debug:
            raise UserFacingError(
                f"Echo request to {normalized_domain} failed: {request_error}"
            ) from None

        return _render_debug_echo_failure(
            domain = normalized_domain,
            debug_json = json_output,
            error_lines = {
                "Status": "failed",
                "Error": request_error,
                "Error type": exc.__class__.__name__,
                "Stage": "request construction",
            },
            outbound_payload = None,
            dns_diagnostics = dns_diagnostics,
            dns_link_context = dns_link_context,
            total_seconds = time.perf_counter() - started_at,
            network_seconds = timing.get("network_seconds", 0.0),
            response_metadata = response_metadata,
            transport_metadata = transport_metadata,
        )
    except Exception as exc:
        if not debug:
            raise

        return _render_debug_echo_failure(
            domain = normalized_domain,
            debug_json = json_output,
            error_lines = {
                "Status": "failed",
                "Error": str(exc) if str(exc) else repr(exc),
                "Error type": exc.__class__.__name__,
                "Stage": "unexpected failure",
            },
            outbound_payload = None,
            dns_diagnostics = dns_diagnostics,
            dns_link_context = dns_link_context,
            total_seconds = time.perf_counter() - started_at,
            network_seconds = timing.get("network_seconds", 0.0),
            response_metadata = response_metadata,
            transport_metadata = transport_metadata,
        )

    total_seconds = time.perf_counter() - started_at
    network_seconds = timing.get("network_seconds", 0.0)
    dns_queries = getattr(dns_diagnostics, "Queries", []) if dns_diagnostics is not None else []
    dnssec_verified = bool(dns_queries) and all(
        getattr(query, "AuthenticData", False) for query in dns_queries
    )
    cdn_detected = _detect_edge_provider(
        _normalize_response_headers(transport_metadata)
    ) is not None

    verification_lines: dict[str, str] = {}
    if verification is not None:
        verification_lines["Schema validated"] = verification.schema
        verification_lines["Required signed headers"] = "were present"
        verification_lines["Canonical payload hash"] = "matched the signed content"
        if verification.dns_lookup_used:
            verification_lines["Signature verified"] = (
                f"via DKIM lookup for selector {verification.selector} "
                f"on {verification.from_value}"
            )
        else:
            verification_lines["Signature verified"] = "with the provided public key"
    else:
        verification_lines["Schema validated"] = response.Schema
        verification_lines["Required signed headers"] = "were present"
        verification_lines["Canonical payload hash"] = "matched the signed content"
        verification_lines["Signature verified"] = (
            f"via DKIM lookup for selector {response.Selector} on {response.From}"
        )
    verification_lines["From matched expected domain"] = response.From
    verification_lines["To matched expected sender"] = response.To
    verification_lines["Subject matched expected echo subject"] = response.Subject
    verification_lines["Correlation matched the request"] = response.Correlation

    dkim_and_dnssec_verified = verification.dns_lookup_used and dnssec_verified
    outbound_payload = None
    if debug:
        wallet, _ = build_wallet_sender(
            normalized_domain,
            key_pair,
            binds_path = binds_path,
            anonymous = anonymous,
        )
        outbound_payload = build_debug_outbound_payload(
            wallet,
            request_message,
            unsigned = unsigned,
        )
    footer_panel = None
    if debug:
        footer_panel = _build_echo_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
            dkim_and_dnssec_verified = dkim_and_dnssec_verified,
            cdn_distribution_detected = cdn_detected)

    if _should_use_textual_echo_view(debug = debug):
        _EchoTextualApp(
            header_panel = _build_echo_header_panel(),
            yaml_sections = _build_echo_textual_sections(
                domain = normalized_domain,
                debug = debug,
                debug_json = False,
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                verification_lines = verification_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            json_sections = _build_echo_textual_sections(
                domain = normalized_domain,
                debug = debug,
                debug_json = True,
                outbound_payload = outbound_payload,
                response_payload = response_payload,
                dns_diagnostics = dns_diagnostics,
                dns_link_context = dns_link_context,
                verification_lines = verification_lines,
                total_seconds = total_seconds,
                network_seconds = network_seconds,
                response_metadata = response_metadata,
                transport_metadata = transport_metadata,
            ),
            footer_panel = footer_panel,
            initial_payload_format = "json" if json_output else "yaml",
        ).run()
        return 0

    if not debug:
        if json_output:
            print_json_payload(parse_debug_payload(response_payload))
            return 0

        print(
            _format_echo_success_metrics(
                total_seconds = total_seconds,
                network_seconds = network_seconds)
        )
        return 0

    print_section_title(f"Verified echo response from {domain}")
    print_labeled_value_lines(
        verification_lines,
        prefix = " - ",
    )
    _print_echo_dns_diagnostics(
        dns_diagnostics,
        json_output = json_output)
    if dns_link_context is not None:
        _print_echo_dns_reference_links(*dns_link_context)
    _print_echo_timing_details(
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        response_metadata = response_metadata)
    _print_echo_edge_details(transport_metadata)
    print()
    DEBUG_CONSOLE.print(footer_panel)
    print()
    return 0
