# pw test

Send a wrapped PollyWeb message test fixture and verify the response:

```bash
pw test ./test.yaml
```

If you omit the path, `pw test` looks for a `pw-tests` directory in the current working directory and runs every `*.yaml` fixture inside it in alphabetical order:

```bash
pw test
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

`pw test` sends only the `Outbound` payload, using the same wallet-backed transport rules as `pw msg`. That means `.dom` recipients are normalized to `.pollyweb.org`, and any explicit `From` value must be `Anonymous` or a UUID bind value. When `From` is omitted or `Anonymous`, the CLI first checks `~/.pollyweb/binds.yaml` for the target domain's bind UUID and uses that as `msg.From`; if none is stored, it falls back to `From: Anonymous`. When `Inbound` is present, the CLI parses the synchronous JSON response and checks that every field in `Inbound` exists in the returned payload with the same value. Extra response fields are allowed. Use the special string `"<uuid>"` in `Inbound` to accept any valid UUID at that field.

If a fixture needs a stored bind value, any string field may use the placeholder `{BindOf(domain)}`. `pw test` resolves it from `~/.pollyweb/binds.yaml` before sending the request, and the lookup uses the same canonical domain normalization as `pw bind`, so `{BindOf(any-hoster.dom)}` and `{BindOf(any-hoster.pollyweb.org)}` resolve the same stored bind. Any string field may also use `"<PublicKey>"`, which resolves to the configured wallet public key from `~/.pollyweb/public.pem` with the PEM framing removed, matching the value sent by `pw bind`.

Use `--anonymous` to ignore any stored bind and force `From: Anonymous`. Use `--unsigned` to keep the selected sender but remove `Hash` and `Signature` before sending.

This makes wrapped fixtures useful for end-to-end checks where you want one file to describe both the request and the expected response.

On success, `pw test` prints one short line per passing fixture: `✅ Passed: <filename-without-extension>`. The default `pw-tests` directory sweep uses the same format, so each passing fixture shows its short file name without printing the received message.

Use `--json` to keep `pw test` compatible with the shared wallet send flags and to switch `--debug` payload rendering from the default YAML-style output to raw JSON. Successful runs still stay concise and print only `✅ Passed: <filename-without-extension>`.

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw test --debug ./test.yaml
```

Print those debug payloads as raw JSON instead:

```bash
pw test --debug --json ./test.yaml
```
