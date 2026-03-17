# pw shell

Open an interactive shell against a domain:

```bash
pw shell vault.example.com
```

This starts a prompt like `pw:vault.example.com> `. Each command you enter is parsed with standard shell token rules and sent to `vault.example.com` as a `Shell@Domain` message whose `From` header is set to the first stored bind for that domain by default, while the body contains the base command and an argument dictionary:

```yaml
Command: send
Arguments:
  amount: "10"
  user: alice
  "0": bob
```

Inputs like `--amount 10` become `amount: "10"`, short flags like `-n 5` become `n: "5"`, and `user=alice` becomes `user: alice`. Plain positional arguments that do not match those patterns stay in `Arguments` as indexed entries such as `"0": bob`.

Shell mode requires a stored bind for the target domain and will ask you to run `pw bind <domain>` first if none exists. Use `--anonymous` to skip that lookup and force anonymous shell requests instead. Use `--unsigned` to keep the selected sender but remove `Hash` and `Signature` before each request. The CLI prints the response body and waits for the next command. Empty commands are ignored. Shell mode exits when you press `Ctrl+D`, press `Ctrl+C`, or when a request error occurs.

Shell mode also stores the last 20 non-blank commands for that exact domain in `~/.pollyweb/history/<domain>.txt` and loads them when the session starts, so the terminal's up/down arrows can navigate recent commands for that domain only. Commands are written to history before the request is sent, so even a command that fails on the server is still available in history.

Print the outbound request payload, the full inbox URL the POST is sent to, and the inbound response body for each shell command as colorized, indented YAML:

```bash
pw shell --debug vault.example.com
```
