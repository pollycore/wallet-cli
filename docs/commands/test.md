# pw test

Send a wrapped PollyWeb message test fixture and verify the response:

```bash
pw test ./test.yaml
```

The file must contain an `Outbound` object and may also contain an `Inbound` object:

```yaml
Outbound:
  To: any-hoster.dom
  Subject: Echo@Domain

Inbound:
  From: any-hoster.pollyweb.org
  To: any-hoster.pollyweb.org
  Subject: Echo@Domain
```

`pw test` sends only the `Outbound` payload, using the same wallet-backed signing and transport rules as `pw msg`. That means `.dom` recipients are normalized to `.pollyweb.org`, and any explicit `From` value must be `Anonymous` or a UUID bind value. When `Inbound` is present, the CLI parses the synchronous JSON response and checks that every field in `Inbound` exists in the returned payload with the same value. Extra response fields are allowed.

This makes wrapped fixtures useful for end-to-end checks where you want one file to describe both the request and the expected response.

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw test --debug ./test.yaml
```
