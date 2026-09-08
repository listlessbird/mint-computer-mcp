# X11 editor input benchmark

Run against an isolated Xvfb or Xephyr display:

```sh
just bench x11-input --display :<isolated-display>
```

Alternatively set `MINT_COMPUTER_INPUT_DISPLAY`. Ambient `DISPLAY` is never
used as a fallback; `--display` takes precedence.

The benchmark launches a separate GTK 3 editor process on that display and
drives its standard multiline TextView through production X11Input methods.
It measures:

- Click until the editor has focus.
- Ctrl+A until the complete seeded text is selected.
- Type 10, 100, or 1,000 characters until the buffer matches the full string.

Each sample resets the editor outside the timed section. A seeded 0-20 ms idle
delay varies input arrival within the frame cycle, avoiding synchronization
with the reset paint. Timing starts immediately before the production input
call. The editor acknowledges completion after both the expected widget state
and a GTK paint cycle. The driver independently checks the returned text,
selection, or focus state.

Both processes use the same monotonic clock. The endpoint is the later of
production input returning and the editor's completion timestamp, excluding
IPC delivery and serialization time. Normal XKB rebuilding, text planning,
XTEST dispatch, application event handling, and GTK drawing are included.
The benchmark never bypasses planning or reuses a text plan.

This replaces the dispatch-only benchmark. GTK paint completion does not
measure physical presentation, compositor latency, or a full editor's plugins
and file handling. Xvfb results represent a real GTK widget and event loop,
not the whole Mint/Cinnamon desktop.

## Dependencies and options

The editor defaults to `/usr/bin/python3` with PyGObject and GTK 3. On
Mint/Ubuntu, the packages are `python3-gi` and `gir1.2-gtk-3.0`.
Use `--editor-python` to select another interpreter with these bindings.
The driver continues to use the project's uv environment.

Defaults are 5 warmup rounds and 100 measured rounds, with five operations per
round. Set `--warmup`, `--iterations`, or `--timeout` as needed.
Timeout defaults to 5 seconds per editor acknowledgement.

Output includes p50/p95 completion latency, successful typing throughput,
per-operation failure counts, and RSS for both processes before warmup,
after warmup, and after the measured operations. Percentiles use successful
samples only. Measured timeouts or verification failures produce a nonzero
exit; startup, warmup, or uncertain input state errors abort the run. RSS also
includes the small timing sample buffers retained by the driver.

The benchmark owns and closes its editor process. It does not start or stop
the selected X server.

## Isolated editor baseline

Measured with `just bench x11-input --display :1` on an owned Xvfb
21.1.12 server, 800×600×24, x86_64 Linux, GTK 3.24.41 and PyGObject 3.48.2.
The run used 5 warmup rounds, 100 measured rounds, and seeded arrival jitter.
All 500 measured operations passed verification. The editor and Xvfb server
were stopped after validation.

| Operation | p50 ms | p95 ms |
| --- | ---: | ---: |
| Click until editor focused | 6.461 | 15.832 |
| Ctrl+A until selection verified | 6.306 | 14.967 |
| Type 10 characters until verified | 14.383 | 31.240 |
| Type 100 characters until verified | 21.545 | 34.942 |
| Type 1,000 characters until verified | 64.382 | 79.943 |

Successful typing throughput was 615, 4,695, and 15,443 characters/s for the
10-, 100-, and 1,000-character workloads respectively. These rates use complete
input-to-editor-completion times; they do not describe individual key spacing.

| RSS phase | Driver KiB | Editor KiB |
| --- | ---: | ---: |
| Before warmup | 32,016 | 98,180 |
| After warmup | 32,532 | 98,464 |
| After 500 measured operations | 32,568 | 98,736 |
| Growth after warmup | 36 | 272 |

These numbers supersede the previous root-window dispatch baseline. They
include a working GTK editor's event loop, text processing, and drawing, while
retaining per-action XKB rebuilding.
