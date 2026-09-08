# X11 input benchmark

Run against an isolated Xvfb or Xephyr display:

```sh
just bench x11-input --display :<isolated-display>
```

Alternatively set `MINT_COMPUTER_INPUT_DISPLAY`. Ambient `DISPLAY` is never
used as a fallback. `--display` takes precedence. The benchmark moves the
pointer to (80, 90), clicks, sends Control_L + a, and types a fixed 44-character
ASCII string. It actively injects input into the selected display.

Defaults are 20 warmup rounds and 1,000 measured rounds, with eight operations
per round. Override them with `--warmup` and `--iterations`.

Snapshot timing uses empty key-name resolution, which acquires and releases the
same fresh XKB keymap/state used by normal actions without looking up symbols.
Resolution and planning timings include their fresh snapshots. Injection-only
throughput uses a prebuilt text plan through the production ownership and
cleanup path. End-to-end typing rebuilds and plans on every action.

Dispatch includes checked XTEST requests and one explicit flush per action.
It does not measure application response or rendering latency. RSS is sampled
after resource and timing-buffer allocation, before warmup, after warmup, and
after the measured operations.

## Initial isolated baseline

Measured with `just bench x11-input --display :1` on an owned Xvfb
21.1.12 server, 800×600×24, x86_64 Linux, libxkbcommon 1.6.0.
The display was stopped after the run.

| Operation | p50 ms | p95 ms |
| --- | ---: | ---: |
| Pointer move | 0.020 | 0.037 |
| Click | 0.043 | 0.087 |
| Key chord, including snapshot and resolution | 1.103 | 2.091 |
| XKB snapshot acquisition and release | 0.073 | 0.136 |
| Key-name resolution, including snapshot | 0.994 | 1.899 |
| Text planning, including snapshot | 4.283 | 6.037 |
| Preplanned text injection | 1.455 | 2.896 |
| End-to-end text action | 5.776 | 8.368 |

Preplanned injection achieved 27,090 codepoints/s; end-to-end typing achieved
7,158 codepoints/s. RSS was 21,968 KiB before warmup, 22,000 KiB after warmup,
and 22,072 KiB after 8,000 measured operations, a post-warmup increase of 72 KiB.

Fresh snapshot acquisition and release took about 0.07 ms at p50. This baseline
supports keeping per-action rebuilding. Resolution and text planning cost more
than rebuilding the snapshot. These Xvfb results do not establish timings on
Mint/Cinnamon or remote X11, and do not justify adding event-driven caching.
