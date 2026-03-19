# pw echo

Send an echo request to a domain and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends an `Echo@Domain` message to the target domain, parses the synchronous response as a PollyWeb message, verifies the response signature using the domain's DKIM key, and checks that the response `From`, `Subject`, and `Correlation` headers match the expected echo flow. The response `To` must match either the normalized target domain or the stored bind UUID for that domain from `~/.pollyweb/binds.yaml`.

On success, the default output stays concise and prints a single verification line that now includes the total request-and-verification duration in milliseconds plus the percentage of that time spent in the network send.

Use `--anonymous` to force `From: Anonymous` and ignore any stored bind lookup. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound echo payload, the full inbox URL the POST is sent to, the inbound signed response, and the DNS verification diagnostics returned by the `pollyweb` package while keeping the same verification checks. The debug view includes the DNS names queried, the returned `DS` and `TXT` values, whether each response was authenticated with the DNSSEC AD flag, and direct links to an MXToolbox DKIM test, a DNSSEC Debugger test, a Google DNS test, and a Google DNS A-record test for the same PollyWeb branch and selector. If verification fails after the response is received, `--debug` still prints those package-owned diagnostics and the external links before returning the error:

```bash
pw echo --debug vault.example.com
```
