# pw chat

Listen for notifier chat events on the configured wallet channel:

```bash
pw chat
```

Use `--debug` to print the websocket URL, wallet channel, and authorization headers used for the AppSync Events connection:

```bash
pw chat --debug
```

`pw chat` reads `Helpers.Notifier` and `Wallet` from `~/.pollyweb/config.yaml`.
The command connects to the notifier's AppSync Events endpoint at `wss://events.<notifier>/event/realtime` and subscribes to `/<namespace>/<wallet>`, currently `/default/<Wallet>`.

On the first successful connection to a given notifier, `pw chat` also publishes a one-time test message into that wallet channel and records that initialization in `~/.pollyweb/chat.yaml`.

Stop listening with `Ctrl+C`.
