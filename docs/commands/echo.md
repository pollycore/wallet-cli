# pw echo

Send an echo request to a domain and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends an `Echo@Domain` message to the target domain, parses the synchronous response as a PollyWeb message, verifies the response signature using the domain's DKIM key, and checks that the response `From`, `Subject`, and `Correlation` headers match the expected echo flow. The response `To` must match either the normalized target domain or the stored bind UUID for that domain from `~/.pollyweb/binds.yaml`.

Use `--anonymous` to force `From: Anonymous` and ignore any stored bind lookup. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound echo payload, the full inbox URL the POST is sent to, the inbound signed response, and DNS verification diagnostics for the PollyWeb branch and DKIM lookup while keeping the same verification checks. The debug view includes the DNS names queried, the returned `DS` and `TXT` values, and whether each response was authenticated with the DNSSEC AD flag. If verification fails after the response is received, `--debug` still prints the DNS diagnostics before returning the error:

```bash
pw echo --debug vault.example.com
```
