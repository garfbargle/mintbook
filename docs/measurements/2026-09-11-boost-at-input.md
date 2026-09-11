# Lifting the cap at the moment of input — 2026-09-11

`pkexec bin/boost-probe 8`. Eight interleaved rounds, one core (`taskset -c 0`),
a fixed Python integer loop at two sizes. On battery, `power-saver`, desktop live,
agent session running, `mintbook-turbo-budget` stopped for the run. Every arm
starts from `max_perf_pct=70` held for 1.5 s, except D.

- **A** — the cap stays at 70.
- **B** — at t0, write `100` to `max_perf_pct` directly, then start the work.
  This models a boost triggered by the key press that starts the work.
- **C** — at t0, write `balanced` to `/run/mintbook-power/want`, then start the
  work. The same trigger through the channel turbo-budget used: path unit,
  `mintbook-power-apply`, `powerprofilesctl`.
- **D** — the cap already at 100 for 1.5 s. The best case.

```
arm  size      runs (ms)                                  median  range
A    3000000   1005  998 1481  910 1003  912 1012  951    1000.5  910-1481
B    3000000    723  678  939  738  713  724  709  697     718    678-939
C    3000000    779  885  975  862  783  768  875  811     836.5  768-975
D    3000000    663  793  868  777  705  668  689  886     741    663-886

A     500000    183  333  185  215  226  203  180  209     206    180-333
B     500000    157  197  161  152  123  150  144  152     152    123-197
C     500000    285  301  188  186  185  190  181  248     189    181-301
D     500000    160  345  148  167  135  165  133  143     154    133-345
```

What the cap costs is A − D: 260 ms on the long task, 52 ms on the short one.

- **B gets all of it back** (282 ms and 54 ms, within noise of D). A cap lifted
  at the moment of input, before the work starts, is as good as no cap.
- **C gets back ~63% on the long task and ~33% on the short one.** The request
  lands while the work is already running.

The arms are mostly separate. They overlap only in the outliers: B's slowest
long run (939) against A's two fastest (910, 912), and B's slowest short run
(197) against A's fastest (180–185).

Not measured:

- A real listener. B writes the cap in the same process that starts the work.
  A listener has to be woken by the X server first.
- What boosting at every key press costs in battery and temperature.
- Package temperature per arm. It was recorded, but not summarised.
