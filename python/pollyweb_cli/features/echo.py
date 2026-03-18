"""Echo feature verification and command implementation."""

from __future__ import annotations

import base64
import hashlib
import json
import urllib.error
from pathlib import Path

from pollyweb import Msg
import pollyweb.msg as pollyweb_msg

from pollyweb_cli.tools.debug import print_echo_response
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.bind import get_first_bind_for_domain, load_binds
from pollyweb_cli.models import EchoResponse
from pollyweb_cli.tools.transport import send_wallet_message


ECHO_SUBJECT = "Echo@Domain"


def parse_and_verify_echo_response(
    payload: str,
    *,
    domain: str,
    request_correlation: str,
    expected_to: str,
    allowed_to: set[str] | None = None
) -> tuple[EchoResponse, object | None]:
    """Parse and verify an echo response, supporting legacy payload variants."""

    try:
        response = Msg.parse(payload)
    except Exception as parse_exc:
        try:
            loaded = json.loads(payload)
            header = loaded["Header"]
            body = loaded.get("Body", {})
            signature_b64 = loaded["Signature"]
            payload_hash = loaded["Hash"]
            canonical_payload = {"Body": body, "Header": header}
            canonical = json.dumps(
                canonical_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        except Exception:
            raise UserFacingError(
                f"Could not parse the echo response from {domain}: {parse_exc}"
            ) from None
        try:
            if payload_hash != hashlib.sha256(canonical).hexdigest():
                raise UserFacingError(
                    f"Echo response from {domain} did not verify: Hash mismatch"
                ) from None

            public_key, key_type = pollyweb_msg._resolve_dkim_public_key(
                header["From"],
                header["Selector"],
            )
            signature_algorithm = header.get("Algorithm") or None
            if public_key is not None and signature_algorithm is None:
                signature_algorithm = pollyweb_msg.signature_algorithm_for_public_key(
                    public_key
                )
            pollyweb_msg.verify_signature(
                public_key,
                base64.b64decode(signature_b64),
                canonical,
                signature_algorithm=signature_algorithm,
                key_type=key_type,
            )
        except UserFacingError:
            raise
        except Exception as exc:
            details = str(exc) or (
                "Invalid signature"
                if exc.__class__.__name__ == "InvalidSignature"
                else exc.__class__.__name__
            )
            raise UserFacingError(
                f"Echo response from {domain} did not verify: {details}"
            ) from None
        parsed_response = EchoResponse(
            From=header["From"],
            To=header["To"],
            Subject=header["Subject"],
            Correlation=header["Correlation"],
            Schema=str(header["Schema"]),
            Selector=header.get("Selector", ""),
            Algorithm=header.get("Algorithm", ""),
        )
        verification = pollyweb_msg.VerificationDetails(
            schema=str(header["Schema"]),
            required_headers_present=True,
            hash_valid=True,
            signature_valid=True,
            dns_lookup_used=True,
            from_value=header["From"],
            to_value=header["To"],
            subject=header["Subject"],
            correlation=header["Correlation"],
            selector=header.get("Selector", ""),
            algorithm=signature_algorithm or "",
        )
    else:
        parsed_response = EchoResponse(
            From=response.From,
            To=response.To,
            Subject=response.Subject,
            Correlation=response.Correlation,
            Schema=str(response.Schema),
            Selector=response.Selector,
            Algorithm=response.Algorithm,
        )
        try:
            verification = (
                response.verify_details() if hasattr(response, "verify_details") else None
            )
            if verification is None:
                response.verify()
        except Exception as exc:
            raise UserFacingError(
                f"Echo response from {domain} did not verify: {exc}"
            ) from None

    if parsed_response.From != domain:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected From value: {parsed_response.From}"
        ) from None
    if parsed_response.Subject != ECHO_SUBJECT:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected Subject: {parsed_response.Subject}"
        ) from None
    if parsed_response.Correlation != request_correlation:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected Correlation: {parsed_response.Correlation}"
        ) from None
    valid_to_values = {expected_to} if allowed_to is None else allowed_to
    if parsed_response.To not in valid_to_values:
        raise UserFacingError(
            f"Echo response from {domain} had an unexpected To value: {parsed_response.To}"
        ) from None

    return parsed_response, verification


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
        allowed_to = {normalized_domain}

        # Some hosts echo back the caller bind UUID instead of the target domain.
        stored_bind = get_first_bind_for_domain(
            normalized_domain,
            load_binds(binds_path))
        if stored_bind is not None:
            allowed_to.add(stored_bind)

        response, verification = parse_and_verify_echo_response(
            response_payload,
            domain=normalized_domain,
            request_correlation=request_message.Correlation,
            expected_to=normalized_domain,
            allowed_to=allowed_to,
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
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Echo request to {domain} failed: {reason}"
        ) from None

    if not debug:
        print("Verified echo response: ✅")
        return 0

    print_echo_response(response_payload)
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
