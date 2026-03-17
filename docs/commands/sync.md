# pw sync

Sync files from `~/.pollyweb/sync/<domain>` to a domain:

```bash
pw sync vault.example.com
```

This command requires a stored bind for the target domain by default. The CLI reads all files under `~/.pollyweb/sync/vault.example.com`, computes a SHA-1 hash for each file, and sends a `Map@Filer` message to the domain.

Each file is represented by its path and hash in the request body:

```yaml
Files:
  /index.html:
    Hash: 2aae6c35c94fcfb415dbe95f408b9ce91ee846ed
```

The server response can include a `Map` identifier and a per-file action list such as `UPLOAD`, `REMOVE`, or other domain-defined actions. The CLI prints those actions to standard output.

Use `--anonymous` to skip the bind lookup and force `From: Anonymous`. Use `--unsigned` to keep the selected sender but remove `Hash` and `Signature` before sending.

Print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body as colorized, indented YAML:

```bash
pw sync --debug vault.example.com
```
