# Security

Supported version: 0.1.x. Run on local files you choose; the runtime does not access the network, invoke a shell, evaluate input code, or modify input files. Reports can contain metric names or URL paths as documented; review them before sharing.

Report a vulnerability through [GitHub private vulnerability reporting](https://github.com/KanadeK/redirect-ledger/security/advisories/new). If private reporting is unavailable, open an issue requesting a private contact without including an exploit, secret, or private data. No response-time guarantee is offered.

The parser uses documented size limits and rejects unsupported input rather than silently treating it as a passing check. Resource limits reduce accidental exhaustion; this is not a sandbox for hostile inputs. Runtime dependencies: none. Development tools and the build backend are installed separately and are not bundled in the wheel.
