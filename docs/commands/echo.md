# pw echo

Send an echo request to a domain and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends an `Echo@Domain` message to the target domain, parses the synchronous `Request`/`Response`/`Meta` envelope through the shared `pollyweb` library, verifies the nested `Response` signature using the domain's DKIM key, and checks that the response `From`, `Subject`, and `Correlation` headers match the expected echo flow. The response `To` must match either the normalized target domain or the stored bind UUID for that domain from `~/.pollyweb/binds.yaml`.

Plain `pw echo` stays concise and prints only the final verification line with total duration and latency percentage.

Use `--json` to print the raw synchronous response instead of the default concise verification line. On an interactive terminal, those JSON payloads now keep the same raw structure but add JSON syntax colors; redirected or scripted output stays plain compact JSON. When you combine `--debug --json`, the debug payload sections switch from the default YAML-style formatting to raw JSON while keeping the same verification, DNS, timing, and summary sections.

`pw echo --debug` adds a top header and a bottom summary box. The summary includes:

- `✅ DKIM and DNSSEC`: the reply signature was verified through DKIM lookup and the returned DNS diagnostics showed authenticated DNSSEC data.
- `✅ Signed message`: the reply carried a valid signed PollyWeb message.
- `✅ CDN distribution` or `⏳ CDN distribution`: transport headers did or did not expose an identifiable edge/CDN provider.
- `⏳ Time <ms>  Network <percent>%`: the total command duration and the share spent in the network send.

Outside `--debug`, the command does not print those boxes.

When `pw echo --debug` runs in an interactive TTY, it now opens a small Textual viewer instead of dumping the finished layout as plain terminal output. That viewer keeps the top and bottom boxes reactive as the terminal width changes. Press `q` or `Esc` to close it. Plain `pw echo` and non-interactive runs keep the normal CLI output for scripts and tests.

Use `--anonymous` to force `From: Anonymous` and ignore any stored bind lookup. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound echo payload, the full inbox URL the POST is sent to, the inbound signed response, and the DNS verification diagnostics returned by the `pollyweb` package while keeping the same verification checks. A target ending in `.dom` is accepted here as shorthand for the matching `.pollyweb.org` domain. The debug view now separates timing into its own `Network timing` section and also prints an `Edge / CDN hints` section with best-effort transport clues such as the request URL, HTTP status, detected edge provider, and PoP when headers like CloudFront's `X-Amz-Cf-Pop` are available. When the echo reply includes `Body.Metadata.TotalExecutionMs` and `Body.Metadata.DownstreamExecutionMs`, the `Network timing` section prints those values too, and `Latency share` includes both the percentage and the measured network milliseconds. It still includes the DNS names queried, the returned `DS` and `TXT` values, whether each response was authenticated with the DNSSEC AD flag, and direct links to an MXToolbox DKIM test, a DNSSEC Debugger test, a Google DNS test, and a Google DNS A-record test for the same PollyWeb branch and selector. For wrapped synchronous replies, the nested `Response.Header` values remain the source of truth for DKIM links, selector reporting, and signature verification. If verification fails after the response is received, `--debug` still prints the inbound payload, those package-owned diagnostics, and the external links before returning the error:

```bash
pw echo --debug vault.example.com
```

```bash
pw echo --debug --json vault.example.com
```
