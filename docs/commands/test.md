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

`pw test` sends only the `Outbound` payload, using the same wallet-backed transport rules as `pw msg`. That means `.dom` recipients are normalized to `.pollyweb.org`, and any explicit `From` value must be `Anonymous` or a UUID bind value. When `From` is omitted or `Anonymous`, the CLI first checks `~/.pollyweb/binds.yaml` for the target domain's bind UUID and uses that as `msg.From`; if none is stored, it falls back to `From: Anonymous`. When `Inbound` is present, the CLI parses the synchronous JSON response and checks that every field in `Inbound` exists in the returned payload with the same value. If an expected field is an empty scalar such as `''` or `null`, the response may include an empty value, the literal string `''`, or omit the field entirely. Extra response fields are allowed. Use the special string `"<uuid>"` in `Inbound` to accept any valid UUID at that field, `"<str>"` to require a present non-empty string value, `"<int>"` to require an integer value, or `"<timestamp>"` to require a valid PollyWeb Zulu timestamp such as `2024-01-02T03:04:05.678Z`.

If a fixture needs a stored bind value, any string field may use the placeholder `{BindOf(domain)}`. `pw test` resolves it from `~/.pollyweb/binds.yaml` before sending the request, and the lookup uses the same canonical domain normalization as `pw bind`, so `{BindOf(any-hoster.dom)}` and `{BindOf(any-hoster.pollyweb.org)}` resolve the same stored bind. Any string field may also use `"<PublicKey>"`, which resolves to the configured wallet public key from `~/.pollyweb/public.pem` with the PEM framing removed, matching the value sent by `pw bind`.

Use `--anonymous` to ignore any stored bind and force `From: Anonymous`. Use `--unsigned` to keep the selected sender but remove `Hash` and `Signature` before sending.

This makes wrapped fixtures useful for end-to-end checks where you want one file to describe both the request and the expected response.

If the target PollyWeb inbox host has no DNS entry, `pw test` reports that directly as `No DNS entry found for domain <domain>.` and includes an MXToolbox A-record lookup link for `pw.<domain>` so you can confirm the missing record outside the CLI.

On success, `pw test` prints one short line per passing fixture in the form `✅ Passed: <filename-without-extension> (<total-ms> ms, <latency>% latency)`. The default `pw-tests` directory sweep uses the same format, so each passing fixture shows its short file name plus timing without printing the received message. When the synchronous response is wrapped and includes `Response.Meta.TotalMs`, `pw test` uses that server-reported total as a timing hint for the displayed total duration and latency share.

If the response payload itself reports a server failure with `Code >= 500`, `pw test` fails the fixture even when the HTTP transport succeeded. During the current transition, the CLI checks both legacy top-level `Code` / `Message` / `Details` fields and the newer `Meta.Code` / `Meta.Message` / `Meta.Details` form so service-side error metadata can move under `Meta` without hiding real test failures.

Use `--json` to keep `pw test` compatible with the shared wallet send flags and to switch `--debug` payload rendering from the default YAML-style output to raw JSON. On an interactive terminal, those JSON payloads keep the same raw structure but add JSON syntax colors; redirected or scripted output stays plain compact JSON. Successful runs still stay concise and print only the one-line `✅ Passed: ...` status with timing.

Print the outbound payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw test --debug ./test.yaml
```

Print those debug payloads as raw JSON instead:

```bash
pw test --debug --json ./test.yaml
```
