# pw echo

Send an echo request to a domain and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends an `Echo@Domain` message to the target domain, parses the synchronous response as a PollyWeb message, verifies the response signature using the domain's DKIM key, and checks that the response `From`, `Subject`, and `Correlation` headers match the expected echo flow. The response `To` must match either the normalized target domain or the stored bind UUID for that domain from `~/.pollyweb/binds.yaml`.

`pw echo` now starts with a minimal boxed header that shows the installed CLI version. Near the end of the command it prints a boxed summary with:

- `✅ DKIM and DNSSEC`: the reply signature was verified through DKIM lookup and the returned DNS diagnostics showed authenticated DNSSEC data.
- `✅ Signed message`: the reply carried a valid signed PollyWeb message.
- `✅ CDN distribution` or `⏳ CDN distribution`: transport headers did or did not expose an identifiable edge/CDN provider.
- `⏳ Duration <ms>  Latency <percent>%`: the total command duration and the share spent in the network send.

After those boxes, the default success path stays concise and prints the verification line with the total request-and-verification duration in milliseconds plus the percentage of that time spent in the network send.

When `pw echo` runs in an interactive TTY, it now opens a small Textual viewer instead of dumping the finished layout as plain terminal output. That viewer keeps the top and bottom boxes reactive as the terminal width changes. Press `q` or `Esc` to close it. Non-interactive runs keep the normal plain CLI output for scripts and tests.

Use `--anonymous` to force `From: Anonymous` and ignore any stored bind lookup. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound echo payload, the full inbox URL the POST is sent to, the inbound signed response, and the DNS verification diagnostics returned by the `pollyweb` package while keeping the same verification checks. The debug view now separates timing into its own `Network timing` section and also prints an `Edge / CDN hints` section with best-effort transport clues such as the request URL, HTTP status, detected edge provider, and PoP when headers like CloudFront's `X-Amz-Cf-Pop` are available. It still includes the DNS names queried, the returned `DS` and `TXT` values, whether each response was authenticated with the DNSSEC AD flag, and direct links to an MXToolbox DKIM test, a DNSSEC Debugger test, a Google DNS test, and a Google DNS A-record test for the same PollyWeb branch and selector. If verification fails after the response is received, `--debug` still prints those package-owned diagnostics and the external links before returning the error:

```bash
pw echo --debug vault.example.com
```
