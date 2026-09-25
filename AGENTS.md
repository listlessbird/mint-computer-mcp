# Project

Linux Mint X11 computer-use MCP server. Python 3.12+, managed with uv.

## Commands

- `just check` runs format checks, lint, types, and non-integration tests.
- `just quick` runs lint and type checks during implementation.
- `just fix` applies formatting and safe lint fixes, then runs the quality gate.
- `just test-integration` runs observation tests on `DISPLAY` and input tests on an isolated Xvfb server. Requires Xvfb.
- `just` lists all commands.

Run relevant checks before finishing a change. Never manipulate the real desktop without explicit authorization.

## Design

- Keep MCP/API models separate from the desktop runtime.
- Use Pydantic at external boundaries; prefer frozen slotted dataclasses internally.
- Prefer explicit domain types, discriminated unions, and exhaustive handling.
- Keep native/untyped dependencies behind narrow adapters. Do not weaken global typing.
- Avoid speculative abstractions and directories. Add structure when code requires it.
- Write focused tests for behavior and invariants. Use snapshots selectively.

## References

`agent-docs/` contains optional gitignored source checkouts. Prefer them when external implementation details matter. Populate selected references with `just agent-docs NAME`.

<!-- polylane:start -->
## Investigating production with Polylane

[Polylane](https://polylane.com/?ref=github.onboarding-pr) is an AI production engineer: it watches deploys, telemetry, incidents, and the infrastructure this repository ships to, investigates problems as they happen, and proposes fixes as pull requests. It is connected to this repository and available to coding agents through the [Polylane MCP server](https://mcp.polylane.com/mcp).

- When a question involves production behaviour (an error, a spike, a deploy, a missing signal), query Polylane through its MCP tools before reasoning from the code alone.
- When debugging a failure, start from the incident or issue Polylane recorded: it carries the evidence an investigation already gathered.
- Polylane reviews pull requests in this repository against the live infrastructure. Read its review comment before merging changes that touch production paths.
<!-- polylane:end -->
