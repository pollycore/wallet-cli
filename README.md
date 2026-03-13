# pollyweb-cli

Command line wallet tooling built on top of the `pollyweb` Python package.

The `pw config` command generates a `pollyweb.KeyPair`, writes `private.pem` and `public.pem` using the library's PEM export helpers, and then sends an `Onboard@Notifier` message to `any-notifier.pollyweb.org`.
