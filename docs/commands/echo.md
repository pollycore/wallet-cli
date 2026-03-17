# pw echo

Send an echo request to a domain and verify the synchronous signed response:

```bash
pw echo vault.example.com
```

This sends an `Echo@Domain` message to the target domain, parses the synchronous response as a PollyWeb message, verifies the response signature using the domain's DKIM key, and checks that the response `From`, `To`, `Subject`, and `Correlation` headers match the expected echo flow.

Use `--anonymous` to force `From: Anonymous` and ignore any stored bind lookup. Use `--unsigned` to remove `Hash` and `Signature` before sending.

Print the outbound echo payload, the full inbox URL the POST is sent to, and the inbound signed response while keeping the same verification checks:

```bash
pw echo --debug vault.example.com
```
