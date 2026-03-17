# pw chat

Listen for notifier chat events on the configured wallet channel:

```bash
pw chat
```

Optionally pass a notifier domain to override `Helpers.Notifier` from `~/.pollyweb/config.yaml` for this run:

```bash
pw chat notifier.example.com
```

Use `--debug` to print the websocket URL, wallet channel, and authorization headers used for the AppSync Events connection:

```bash
pw chat notifier.example.com --debug
```

Use `--test` to publish a `"TEST"` message to the wallet channel immediately after the websocket connection is acknowledged:

```bash
pw chat notifier.example.com --test
```

Use `--unsigned` to build the notifier authorization token without `Hash` or `Signature`. Use `--anonymous` to ignore the configured wallet ID for this session and connect on `/default/Anonymous` instead.

`pw chat` always reads `Wallet` from `~/.pollyweb/config.yaml`.
If you do not pass a domain, it also reads `Helpers.Notifier` from that file.
If you pass a domain, that positional argument overrides `Helpers.Notifier` for the current command.
The command connects to the notifier's AppSync Events endpoint at `wss://events.<notifier>/event/realtime` and subscribes to `/<namespace>/<wallet>`, currently `/default/<Wallet>` or `/default/Anonymous` when you use `--anonymous`.

Stop listening with `Ctrl+C`.
