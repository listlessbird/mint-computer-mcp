# mint-computer-mcp

Computer-use MCP server for Linux Mint X11 desktops. Currently a project scaffold with a strict API model base; desktop automation is not implemented yet.

## Development

Use Python 3.12, uv, and just. Install the locked dependencies and local Git hooks:

```sh
just sync
just hooks
```

Run the checks:

```sh
just check
```

Use `just quick` for lint and type checks while editing, `just test` for non-integration tests, and `just coverage` for branch coverage. `just check-all` includes integration tests and requires an explicitly authorized X11 test desktop. Run `just` to list all commands.

Pass pytest arguments through with `just pytest -k "model or geometry"`, or select a target with `just test-one tests/unit/test_model.py`.

Apply safe lint fixes and formatting, then run the quality gate:

```sh
just fix
```

Commit hooks run Ruff fixes, formatting, and basedpyright. Run them manually with `just hooks-all`. Hooks operate on Git-tracked files, so newly created files must be staged first. Tests stay outside the commit hook.

Ruff requires annotations; basedpyright checks types in `all` mode. Add small local stubs under `typings/` when native dependencies need them instead of disabling global checks. Pydantic models validate external inputs; keep internal domain types independent of Pydantic.

pytest uses strict mode and treats warnings as errors. Hypothesis is available for invariants and Syrupy for selective snapshots. Review snapshot diffs before accepting them with `just pytest --snapshot-update`. Coverage measures branches without enforcing a percentage target.

Future desktop tests belong under `tests/integration/` and must use the `integration` marker. Run `just test-integration` only against an explicitly authorized test desktop, serialized.

Both entry points currently run the CLI placeholder:

```sh
just run
just run-module
```

## Local source references

Download only the references needed for the current subsystem:

```sh
just agent-docs pydantic mcp-python-sdk
```

Run `just agent-docs` without arguments to list available names. Checkouts and their generated revision index live in gitignored `agent-docs/`. Re-running the command updates selected checkouts with fast-forward-only pulls; these are moving upstream references, not pinned dependencies.
