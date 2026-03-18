"""Echo feature verification and command implementation."""

from __future__ import annotations

from dataclasses import asdict
import json
import urllib.error
from pathlib import Path
from urllib.parse import quote

from pollyweb import Msg, MsgValidationError

from pollyweb_cli.tools.debug import print_debug_payload, print_echo_response
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import (
    describe_bind_network_error,
    get_first_bind_for_domain,
    load_binds,
)
from pollyweb_cli.tools.transport import send_wallet_message


ECHO_SUBJECT = "Echo@Domain"
ALLOWED_ECHO_RESPONSE_FIELDS = frozenset({"Body", "Hash", "Header", "Signature"})


def _extract_response_header(
    payload: str
) -> dict[str, object] | None:
    """Extract the raw response header when the payload is valid JSON."""

    try:
        loaded_payload = json.loads(payload)
    except json.JSONDecodeError:
        return None

    header = loaded_payload.get("Header")
    if not isinstance(header, dict):
        return None

    return header


def _echo_dns_reference_links(
    domain: str,
    selector: str
) -> dict[str, str]:
    """Build click-through DNS inspection links for the verified selector."""

    branch = f"pw.{domain}"

    return {
        "MXToolbox DKIM test": (
            "https://mxtoolbox.com/SuperTool.aspx?action="
            f"{quote(f'dkim:{branch}:{selector}', safe='')}&run=toolpage"
        ),
        "DNSSEC Debugger test": f"https://dnssec-debugger.verisignlabs.com/{branch}",
        "Google DNS test": f"https://dns.google/query?name={branch}",
        "Google DNS A record test": f"https://dns.google/resolve?name={branch}&type=A",
    }


def _echo_dns_context(
    payload: str,
    *,
    fallback_domain: str
) -> tuple[str, str] | None:
    """Extract the response domain and selector used for echo verification."""

    header = _extract_response_header(payload)
    if header is None:
        return None

    selector = header.get("Selector")
    if not isinstance(selector, str) or selector == "":
        return None

    from_value = header.get("From")
    domain = from_value if isinstance(from_value, str) and from_value else fallback_domain

    return domain, selector


def _print_echo_dns_diagnostics(
    diagnostics
) -> None:
    """Render DNS verification diagnostics for the echo debug path."""

    if diagnostics is None:
        return

    print_debug_payload(
        "DNS verification diagnostics",
        asdict(diagnostics))


def _print_echo_dns_reference_links(
    domain: str,
    selector: str
) -> None:
    """Render click-through external DNS inspection links."""

    print()
    print("External DNS checks:")

    for label, url in _echo_dns_reference_links(
        domain,
        selector).items():
        print(f"{label}: {url}")

    print()

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


def cmd_echo(
    domain: str,
    *,
    debug: bool,
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

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        response_payload, request_message, normalized_domain = send_wallet_message(
            domain=domain,
            subject=ECHO_SUBJECT,
            body={},
            key_pair=key_pair,
            debug=debug,
            binds_path=binds_path,
            anonymous=anonymous,
            unsigned=unsigned,
        )
        if debug:
            dns_link_context = _echo_dns_context(
                response_payload,
                fallback_domain = normalized_domain)
        allowed_to = {normalized_domain}

        # Some hosts echo back the caller bind UUID instead of the target domain.
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

        dns_diagnostics = verification.dns_diagnostics
    except UserFacingError as exc:
        dns_diagnostics = getattr(exc, "diagnostics", dns_diagnostics)
        if debug:
            _print_echo_dns_diagnostics(dns_diagnostics)
            if dns_link_context is not None:
                _print_echo_dns_reference_links(*dns_link_context)
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
        reason = describe_bind_network_error(
            domain,
            exc.reason)
        raise UserFacingError(
            f"Echo request to {domain} failed: {reason}"
        ) from None

    if not debug:
        print("✅ Verified echo response")
        return 0

    print_echo_response(response_payload)
    _print_echo_dns_diagnostics(dns_diagnostics)
    if dns_link_context is not None:
        _print_echo_dns_reference_links(*dns_link_context)
    print(f"Verified echo response from {domain}:")
    if verification is not None:
        print(f" - Schema validated: {verification.schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        if verification.dns_lookup_used:
            print(
                f" - Signature verified via DKIM lookup for selector "
                f"{verification.selector} on {verification.from_value}"
            )
        else:
            print(" - Signature verified with the provided public key")
    else:
        print(f" - Schema validated: {response.Schema}")
        print(" - Required signed headers were present")
        print(" - Canonical payload hash matched the signed content")
        print(
            f" - Signature verified via DKIM lookup for selector {response.Selector} "
            f"on {response.From}"
        )
    print(f" - From matched expected domain: {response.From}")
    print(f" - To matched expected sender: {response.To}")
    print(f" - Subject matched expected echo subject: {response.Subject}")
    print(f" - Correlation matched the request: {response.Correlation}")
    return 0
