# What background I/O actually delays — 2026-09-06

Three probes, in the order they were run, including the two that found nothing.

## 1. A 512 MB write does not disturb the desktop

`bin/io-stall` — X round trips sampled throughout a 512 MB `dd ... conv=fsync`.

```
quiet    n=10  median  6 ms   p95 23 ms   io PSI some avg10 max  5.9
writing  n=11  median  6 ms   p95 33 ms   io PSI some avg10 max  8.2
```

Nothing. The write finished in about two seconds and never approached
`dirty_ratio`'s ~1.5 GB.

## 2. A metadata storm does not either

`MODE=find bin/io-stall` — a full `find / -xdev` while sampling.

```
quiet    n=15   median 12 ms   p95 25 ms   io PSI some avg10 max  5.3
writing  n=141  median 14 ms   p95 29 ms   io PSI some avg10 max 15.8
```

I/O pressure triples. X does not care. **Two flaws, both mine:** the X server
does no disk I/O, so X round trips are the wrong probe for an I/O question; and
an earlier `find` had already warmed the dentry cache, so this second walk barely
reached the device.

## 3. Contention nearly doubles a cold application read

`bin/cold-read` — evict `/usr/lib/firefox/libxul.so` (177 MB) with
`posix_fadvise(DONTNEED)`, time reading it back, against a competitor that
evicts and re-reads three other large files in a loop so every byte comes off
the disk. Three interleaved pairs.

```
quiet      n=3  median   905 ms   min 883   max 929
contended  n=3  median  1668 ms   min 1630  max 1671

contention costs +763 ms (1.8x)
worst within-arm spread: 46 ms
```

The arms do not overlap. Eviction is real and separately confirmed: the same
read is **881 ms** evicted and **85 ms** cached — a factor of ten.

## What this means

Background I/O on this machine costs **application launches**, not the
compositor. Anything that protects the desktop's *drawing* from a busy disk is
solving a problem that does not exist here; anything that keeps launches out of
the queue, or out of the disk entirely, is worth real time.

## A tooling bug found and removed

Both probes originally reported page-cache residency via `mincore` over a
`MAP_PRIVATE` mapping. It reported **100% resident for a file that had just been
evicted** — contradicted by the 881 ms read that followed. The residency
reporting was removed rather than fixed: a timed read answers the same question
and cannot lie about it.
