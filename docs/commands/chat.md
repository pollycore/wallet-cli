# pw chat

Listen for notifier chat events on the configured wallet channel:

```bash
pw chat
```

Use `--debug` to print the websocket URL, wallet channel, and authorization headers used for the AppSync Events connection:

```bash
pw chat --debug
```

Use `--test` to publish a `"TEST"` message to the wallet channel immediately after the websocket connection is acknowledged:

```bash
pw chat --test
```

`pw chat` reads `Helpers.Notifier` and `Wallet` from `~/.pollyweb/config.yaml`.
The command connects to the notifier's AppSync Events endpoint at `wss://events.<notifier>/event/realtime` and subscribes to `/<namespace>/<wallet>`, currently `/default/<Wallet>`.

Stop listening with `Ctrl+C`.
