"""Data models used by CLI features."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EchoResponse:
    """Normalized echo response fields used after verification."""

    From: str
    To: str
    Subject: str
    Correlation: str
    Schema: str
    Selector: str = ""
    Algorithm: str = ""


@dataclass(frozen=True)
class DnsQueryDiagnostic:
    """One DNS query result captured for debug rendering."""

    Name: str
    Type: str
    ResponseCode: str
    AuthenticData: bool
    Answers: list[str]
    Error: str = ""


@dataclass(frozen=True)
class EchoDnsDiagnostics:
    """Collected DNS diagnostics for one echo response verification."""

    Domain: str
    PollyWebBranch: str
    Selector: str
    DkimName: str
    DnssecRequested: bool
    Nameservers: list[str]
    Queries: list[DnsQueryDiagnostic]
    Error: str = ""
