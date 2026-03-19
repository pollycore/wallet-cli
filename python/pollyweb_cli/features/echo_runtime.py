"""Command orchestration helpers for the `pw echo` feature."""

from __future__ import annotations

import time
import urllib.error
from pathlib import Path

from pollyweb import MsgValidationError

from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import get_first_bind_for_domain, load_binds
from pollyweb_cli.features.echo_models import ECHO_SUBJECT, _EchoCommandFailure, _EchoCommandSuccess
from pollyweb_cli.features.echo_rendering import _build_echo_error_footer_panel, _build_echo_footer_panel
from pollyweb_cli.features.echo_response import (
    _build_echo_failure_verification_lines,
    _describe_echo_network_error,
    _extract_echo_response_metadata,
    _parse_echo_response,
    _rewrite_echo_request_validation_error,
    _to_echo_user_facing_error,
)
from pollyweb_cli.features.echo_sections import (
    _build_echo_error_textual_sections,
    _build_echo_textual_sections,
    _detect_edge_provider,
    _echo_dns_context,
    _normalize_response_headers,
)
from pollyweb_cli.tools.debug import parse_debug_payload
from pollyweb_cli.tools.transport import build_debug_outbound_payload, build_wallet_sender, send_wallet_message


def _initial_echo_payload_format(
    *,
    json_output: bool
) -> str:
    """Return the initial interactive payload format for debug echo views."""

    if json_output:
        return "raw"

    return "yaml"


def _build_textual_echo_sections(
    resolved: _EchoCommandSuccess | _EchoCommandFailure,
    *,
    debug: bool
) -> tuple[list, list, list, object, int]:
    """Build all Textual section views before launching the app."""

    if isinstance(resolved, _EchoCommandFailure):
        return (
            _build_echo_error_textual_sections(
                domain = resolved.normalized_domain,
                payload_format = "yaml",
                outbound_payload = resolved.outbound_payload,
                response_payload = resolved.response_payload,
                parsed_response_payload = resolved.parsed_response_payload,
                verification_lines = resolved.verification_lines,
                dns_diagnostics = resolved.dns_diagnostics,
                dns_link_context = resolved.dns_link_context,
                error_lines = resolved.error_lines,
                total_seconds = resolved.total_seconds,
                network_seconds = resolved.network_seconds,
                response_metadata = resolved.response_metadata,
                transport_metadata = resolved.transport_metadata,
            ),
            _build_echo_error_textual_sections(
                domain = resolved.normalized_domain,
                payload_format = "json",
                outbound_payload = resolved.outbound_payload,
                response_payload = resolved.response_payload,
                parsed_response_payload = resolved.parsed_response_payload,
                verification_lines = resolved.verification_lines,
                dns_diagnostics = resolved.dns_diagnostics,
                dns_link_context = resolved.dns_link_context,
                error_lines = resolved.error_lines,
                total_seconds = resolved.total_seconds,
                network_seconds = resolved.network_seconds,
                response_metadata = resolved.response_metadata,
                transport_metadata = resolved.transport_metadata,
            ),
            _build_echo_error_textual_sections(
                domain = resolved.normalized_domain,
                payload_format = "raw",
                outbound_payload = resolved.outbound_payload,
                response_payload = resolved.response_payload,
                parsed_response_payload = resolved.parsed_response_payload,
                verification_lines = resolved.verification_lines,
                dns_diagnostics = resolved.dns_diagnostics,
                dns_link_context = resolved.dns_link_context,
                error_lines = resolved.error_lines,
                total_seconds = resolved.total_seconds,
                network_seconds = resolved.network_seconds,
                response_metadata = resolved.response_metadata,
                transport_metadata = resolved.transport_metadata,
            ),
            resolved.footer_panel,
            1,
        )

    return (
        _build_echo_textual_sections(
            domain = resolved.normalized_domain,
            debug = debug,
            payload_format = "yaml",
            outbound_payload = resolved.outbound_payload,
            response_payload = resolved.response_payload,
            parsed_response_payload = resolved.parsed_response_payload,
            dns_diagnostics = resolved.dns_diagnostics,
            dns_link_context = resolved.dns_link_context,
            verification_lines = resolved.verification_lines,
            total_seconds = resolved.total_seconds,
            network_seconds = resolved.network_seconds,
            response_metadata = resolved.response_metadata,
            transport_metadata = resolved.transport_metadata,
        ),
        _build_echo_textual_sections(
            domain = resolved.normalized_domain,
            debug = debug,
            payload_format = "json",
            outbound_payload = resolved.outbound_payload,
            response_payload = resolved.response_payload,
            parsed_response_payload = resolved.parsed_response_payload,
            dns_diagnostics = resolved.dns_diagnostics,
            dns_link_context = resolved.dns_link_context,
            verification_lines = resolved.verification_lines,
            total_seconds = resolved.total_seconds,
            network_seconds = resolved.network_seconds,
            response_metadata = resolved.response_metadata,
            transport_metadata = resolved.transport_metadata,
        ),
        _build_echo_textual_sections(
            domain = resolved.normalized_domain,
            debug = debug,
            payload_format = "raw",
            outbound_payload = resolved.outbound_payload,
            response_payload = resolved.response_payload,
            parsed_response_payload = resolved.parsed_response_payload,
            dns_diagnostics = resolved.dns_diagnostics,
            dns_link_context = resolved.dns_link_context,
            verification_lines = resolved.verification_lines,
            total_seconds = resolved.total_seconds,
            network_seconds = resolved.network_seconds,
            response_metadata = resolved.response_metadata,
            transport_metadata = resolved.transport_metadata,
        ),
        resolved.footer_panel,
        0,
    )


def _build_echo_failure_result(
    *,
    normalized_domain: str,
    error_lines: dict[str, str],
    request_message,
    response_payload: str | None,
    dns_diagnostics,
    dns_link_context: tuple[str, str] | None,
    total_seconds: float,
    network_seconds: float,
    response_metadata: object | None,
    transport_metadata: dict[str, object],
    key_pair,
    binds_path: Path,
    anonymous: bool,
    unsigned: bool
) -> _EchoCommandFailure:
    """Build one fully-renderable debug failure result."""

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

    return _EchoCommandFailure(
        normalized_domain = normalized_domain,
        error_lines = error_lines,
        outbound_payload = outbound_payload,
        response_payload = response_payload,
        parsed_response_payload = (
            parse_debug_payload(response_payload)
            if response_payload is not None
            else None
        ),
        verification_lines = _build_echo_failure_verification_lines(response_payload),
        dns_diagnostics = dns_diagnostics,
        dns_link_context = dns_link_context,
        response_metadata = response_metadata,
        transport_metadata = transport_metadata,
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        footer_panel = _build_echo_error_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
        ),
    )


def _resolve_echo_command(
    domain: str,
    *,
    debug: bool,
    transport_debug: bool = False,
    json_output: bool,
    config_dir,
    binds_path: Path,
    unsigned: bool,
    anonymous: bool,
    require_configured_keys,
    load_signing_key_pair
) -> _EchoCommandSuccess | _EchoCommandFailure:
    """Execute the echo request and return render-ready success or failure data."""

    dns_diagnostics = None
    dns_link_context: tuple[str, str] | None = None
    timing: dict[str, float] = {}
    transport_metadata: dict[str, object] = {}
    started_at = time.perf_counter()
    normalized_domain = domain
    response_payload: str | None = None
    request_message = None
    response_metadata: object | None = None
    key_pair = None

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        response_payload, request_message, normalized_domain = send_wallet_message(
            domain = domain,
            subject = ECHO_SUBJECT,
            body = {},
            key_pair = key_pair,
            debug = transport_debug,
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
            response = _parse_echo_response(
                response_payload,
                normalized_domain)
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

        response_metadata = _extract_echo_response_metadata(
            response_payload,
            response,
        )
        dns_diagnostics = verification.dns_diagnostics
    except UserFacingError as exc:
        if not debug:
            raise

        dns_diagnostics = getattr(exc, "diagnostics", dns_diagnostics)
        return _build_echo_failure_result(
            normalized_domain = normalized_domain,
            error_lines = {
                "Status": "failed",
                "Error": str(exc),
                "Error type": exc.__class__.__name__,
            },
            request_message = request_message,
            response_payload = response_payload,
            dns_diagnostics = dns_diagnostics,
            dns_link_context = dns_link_context,
            total_seconds = time.perf_counter() - started_at,
            network_seconds = timing.get("network_seconds", 0.0),
            response_metadata = response_metadata,
            transport_metadata = transport_metadata,
            key_pair = key_pair,
            binds_path = binds_path,
            anonymous = anonymous,
            unsigned = unsigned,
        )
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

        return _build_echo_failure_result(
            normalized_domain = normalized_domain,
            error_lines = {
                "Status": "failed",
                "Error": request_error,
                "Error type": exc.__class__.__name__,
                "Stage": "request construction",
            },
            request_message = None,
            response_payload = response_payload,
            dns_diagnostics = dns_diagnostics,
            dns_link_context = dns_link_context,
            total_seconds = time.perf_counter() - started_at,
            network_seconds = timing.get("network_seconds", 0.0),
            response_metadata = response_metadata,
            transport_metadata = transport_metadata,
            key_pair = key_pair,
            binds_path = binds_path,
            anonymous = anonymous,
            unsigned = unsigned,
        )
    except Exception as exc:
        if not debug:
            raise

        return _build_echo_failure_result(
            normalized_domain = normalized_domain,
            error_lines = {
                "Status": "failed",
                "Error": str(exc) if str(exc) else repr(exc),
                "Error type": exc.__class__.__name__,
                "Stage": "unexpected failure",
            },
            request_message = None,
            response_payload = response_payload,
            dns_diagnostics = dns_diagnostics,
            dns_link_context = dns_link_context,
            total_seconds = time.perf_counter() - started_at,
            network_seconds = timing.get("network_seconds", 0.0),
            response_metadata = response_metadata,
            transport_metadata = transport_metadata,
            key_pair = key_pair,
            binds_path = binds_path,
            anonymous = anonymous,
            unsigned = unsigned,
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
    verification_lines["From matched expected domain"] = response.From
    verification_lines["To matched expected sender"] = response.To
    verification_lines["Subject matched expected echo subject"] = response.Subject
    verification_lines["Correlation matched the request"] = response.Correlation

    outbound_payload = None
    footer_panel = None
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
        footer_panel = _build_echo_footer_panel(
            total_seconds = total_seconds,
            network_seconds = network_seconds,
            dkim_and_dnssec_verified = verification.dns_lookup_used and dnssec_verified,
            cdn_distribution_detected = cdn_detected)

    return _EchoCommandSuccess(
        normalized_domain = normalized_domain,
        response_payload = response_payload,
        parsed_response_payload = parse_debug_payload(response_payload),
        outbound_payload = outbound_payload,
        verification_lines = verification_lines,
        dns_diagnostics = dns_diagnostics,
        dns_link_context = dns_link_context,
        response_metadata = response_metadata,
        transport_metadata = transport_metadata,
        total_seconds = total_seconds,
        network_seconds = network_seconds,
        footer_panel = footer_panel,
    )
