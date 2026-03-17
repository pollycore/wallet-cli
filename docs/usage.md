# Usage

Command-specific guides:

- [commands/config.md](commands/config.md) for `pw config`
- [commands/bind.md](commands/bind.md) for `pw bind`
- [commands/echo.md](commands/echo.md) for `pw echo`
- [commands/msg.md](commands/msg.md) for `pw msg`
- [commands/test.md](commands/test.md) for `pw test`
- [commands/shell.md](commands/shell.md) for `pw shell`
- [commands/chat.md](commands/chat.md) for `pw chat`
- [commands/sync.md](commands/sync.md) for `pw sync`

Quick examples:

```bash
pw version
pw config
pw bind vault.example.com
pw echo vault.example.com
pw msg ./message.yaml
pw msg '{"To":"vault.example.com","Subject":"Echo@Domain","Body":{"Ping":"pong"}}'
pw msg To:any-domain.org Subject:topic@role DynamicBodyProperty:123
pw test ./test.yaml
pw chat
pw shell vault.example.com
pw sync vault.example.com
```
