# Project

Linux Mint X11 computer-use MCP server. Python 3.12+, managed with uv.

## Commands

- `just check` runs format checks, lint, types, and non-integration tests.
- `just quick` runs lint and type checks during implementation.
- `just fix` applies formatting and safe lint fixes, then runs the quality gate.
- `just test-integration` runs tests requiring an explicitly authorized X11 test desktop.
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
