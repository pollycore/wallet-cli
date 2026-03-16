"""Argument parser construction for the CLI entrypoint."""

from __future__ import annotations

import argparse


def build_parser(get_cli_version) -> argparse.ArgumentParser:
    """Construct the top-level command parser."""

    parser = argparse.ArgumentParser(
        prog="pw",
        description="PollyWeb command line wallet.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {get_cli_version()}",
        help="Show the installed CLI version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command")

    config_parser = subparsers.add_parser(
        "config",
        help="Generate a PollyWeb key pair in ~/.pollyweb.",
    )
    config_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing key pair.",
    )

    bind_parser = subparsers.add_parser(
        "bind",
        help="Bind the configured wallet key to a domain.",
    )
    bind_parser.add_argument("domain", help="Domain that will receive the bind request.")
    bind_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound bind payloads.",
    )

    echo_parser = subparsers.add_parser(
        "echo",
        help="Send an echo request to a domain and verify the signed response.",
    )
    echo_parser.add_argument(
        "domain",
        help="Domain that will receive the echo request.",
    )
    echo_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound echo payloads.",
    )

    shell_parser = subparsers.add_parser(
        "shell",
        help="Open an interactive shell against a domain.",
    )
    shell_parser.add_argument(
        "domain",
        help="Domain that will receive shell commands.",
    )
    shell_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound shell payloads.",
    )

    sync_parser = subparsers.add_parser(
        "sync",
        help="Sync files from ~/.pollyweb/sync/{domain} to a domain.",
    )
    sync_parser.add_argument(
        "domain",
        help="Domain that will receive the sync request.",
    )
    sync_parser.add_argument(
        "--debug",
        action="store_true",
        help="Print outbound and inbound sync payloads.",
    )

    return parser
