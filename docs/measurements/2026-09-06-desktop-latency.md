# X round-trip latency under load — 2026-09-06

`bin/desktop-latency 3`. Three interleaved pairs, a 4-thread busy load, twelve
`xdpyinfo` round-trip samples per arm. `xdpyinfo` is one fork followed by a few
hundred X round trips, so its wall time is dominated by how quickly the server
gets scheduled.

```
idle       n=12  median  16 ms   p95  34 ms   max  35 ms
competing  n=36  median  40 ms   p95  64 ms   max  95 ms
niced      n=36  median  27 ms   p95  41 ms   max  84 ms
```

Load costs the X server **+24 ms** of median round trip. Separating priorities
gives **13 ms of that back** — a bit over half — and p95 falls from 64 ms to
41 ms.

**This is a proxy.** It nices the *competitor* down, because raising Xorg up
needs `CAP_SYS_NICE` and this session has no root. The mechanism is the same one
`bin/desktop-nice` uses from the other end; the sizes need not be identical.
