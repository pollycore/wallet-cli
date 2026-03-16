"""Sync feature helpers and command implementation."""

from __future__ import annotations

import hashlib
import json
import urllib.error
from pathlib import Path

from pollyweb_cli.features.bind_feature import get_first_bind_for_domain, load_binds
from pollyweb_cli.errors import UserFacingError
from pollyweb_cli.features.shell_feature import get_shell_from_value
from pollyweb_cli.tools.transport import post_signed_message


SYNC_SUBJECT = "Map@Filer"


def build_sync_files_map(domain: str, sync_dir: Path) -> dict[str, dict[str, str]]:
    """Build the file hash map for the sync request body."""

    sync_domain_dir = sync_dir / domain
    if not sync_domain_dir.exists():
        raise UserFacingError(
            f"Sync directory {sync_domain_dir} does not exist."
        )
    files: dict[str, dict[str, str]] = {}
    for file_path in sorted(sync_domain_dir.rglob("*")):
        if file_path.is_file():
            relative = "/" + file_path.relative_to(sync_domain_dir).as_posix()
            sha1 = hashlib.sha1(file_path.read_bytes()).hexdigest()
            files[relative] = {"Hash": sha1}
    return files


def cmd_sync(
    domain: str,
    *,
    debug: bool,
    config_dir: Path,
    binds_path: Path,
    sync_dir: Path,
    require_configured_keys,
    load_signing_key_pair
) -> int:
    """Run the sync command and print the server-side file actions."""

    try:
        require_configured_keys()
        key_pair = load_signing_key_pair()
        binds = load_binds(binds_path)
    except FileNotFoundError:
        raise UserFacingError(
            f"Missing PollyWeb keys in {config_dir}. Run `pw config` first."
        ) from None
    except ValueError as exc:
        raise UserFacingError(str(exc)) from None

    bind_value = get_first_bind_for_domain(domain, binds)
    if bind_value is None:
        raise UserFacingError(
            f"No bind stored for {domain}. Run `pw bind {domain}` first."
        ) from None
    from_value = get_shell_from_value(bind_value)
    files = build_sync_files_map(domain, sync_dir)

    try:
        response_payload = post_signed_message(
            domain=domain,
            subject=SYNC_SUBJECT,
            body={"Files": files},
            key_pair=key_pair,
            debug=debug,
            from_value=from_value,
        )
    except urllib.error.HTTPError as exc:
        raise UserFacingError(
            f"Sync request to {domain} failed with HTTP {exc.code}."
        ) from None
    except urllib.error.URLError as exc:
        reason = exc.reason if isinstance(exc.reason, str) else repr(exc.reason)
        raise UserFacingError(
            f"Sync request to {domain} failed: {reason}"
        ) from None

    try:
        response = json.loads(response_payload)
    except json.JSONDecodeError:
        raise UserFacingError(
            f"Could not parse sync response from {domain}."
        ) from None

    map_id = response.get("Map")
    response_files = response.get("Files", {})

    if map_id:
        print(f"Map: {map_id}")
    for file_path, file_info in response_files.items():
        action = file_info.get("Action", "")
        print(f"{action}: {file_path}")

    return 0
