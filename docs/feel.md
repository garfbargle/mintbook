# Feel — ideas for perceived speed, and one measurement that reframes them

Every pass in this repository so far has asked *how much work is the machine
doing*. This one asks a different question: **how fast does it feel**, which is
a different quantity and has different levers.

Nothing here is applied. This is a candidate list, ranked, written on
**2026-09-06** after probing the live machine. One measurement was taken, and it
changes how the rest should be read.

---

## The measurement: there is no burst state to protect

Two busy-loop threads for 48 s. On AC, `balanced`, `max_perf_pct=100`, desktop
live with an Electron app open.

```
   t      MHz_avg   PkgTemp
  2.8s      1900     95.0
  5.6s      1800     94.0
 ...        1700-1940  94-95
 48.0s      1900     94.0
```

At rest under the same desktop, the package sits at **71–77 °C**. Under load it
reaches its **95 °C** limit inside the first sample — under three seconds — and
stays pinned there for as long as the load lasts, at **1700–1900 MHz** against a
2400 MHz maximum.

So: **the binding constraint is thermal, always, and it binds within about three
seconds.** There is no sustained fast state on AC that the battery profile is
taking away. What the machine actually has is roughly three seconds of turbo,
followed by ~75% of maximum clock indefinitely.

Limits of this measurement, which are not small:

- `MHz_avg` is `/proc/cpuinfo` averaged over four logical CPUs, two of them idle.
  Read it as indicative of the ceiling, not as a per-core clock.
- RAPL `energy_uj` is not readable without root, so there are **no watts** here.
- The "at rest" figure is a live desktop with an agent session running, not a
  clean idle. It is the operating reality, not a baseline.

### What follows from it

**The battery cap costs the burst and almost nothing else.** `max_perf_pct=70`
is ≈1680 MHz, which is at the bottom of the 1700–1900 MHz band the machine
sustains anyway. After the first few seconds the cap is very nearly free; before
them it removes the entire fast window — and the first few seconds is the only
part of a click a person perceives. *This is an inference from the numbers above,
not a measurement.* Testing it means timing a short interactive-length task
(cold app launch, page render) capped and uncapped, not a long benchmark.

**Idle temperature is a performance parameter.** Burst duration is proportional
to thermal headroom, and headroom here is ~15 °C. Every watt taken out of the
idle draw — panel brightness, compositor, background CPU — buys burst *length*,
not just battery. That reframes the whole power-tuning history in this repository
as latency work.

---

## Ranked candidates

### 1. Keyboard repeat is at the X11 default — 500 ms delay, 20 Hz

```
auto repeat delay:  500    repeat rate:  20
```

Nothing sets it, in `xfconf`, `~/.profile`, or `Xsession.d`. macOS on this same
hardware ships far faster. Every held arrow key, every backspace run, waits half
a second and then crawls. `xset r rate 200 45` changes no work the machine does
and changes how it feels to use immediately. Highest felt value per minute of
effort on this list, and the undo is `xset r rate 500 20`.

### 2. Fix the worst moments, not the average

The SSD controller takes **one command at a time** (`qdepth_one`), and
`nr_requests` is **2**. Meanwhile these are enabled and dump heavy IO at it on
their own schedule: `apt-daily`, `apt-daily-upgrade`, `plocate-updatedb`,
`man-db`, `e2scrub_all`, `motd-news`, `fwupd-refresh`, `anacron`.

These are the "why is it frozen" moments. They do not move any average and they
are what a person remembers. `IOSchedulingClass=idle` and `Nice=19` drop-ins, or
`OnlyRunWhenOnAC`-style gating, would cost nothing measurable and remove them.
`io PSI some avg10` was **3.49** while writing this — the machine is already
waiting on that disk.

### 3. Cap the sustained, not the burst

Instead of a flat `max_perf_pct=70` on battery: leave it at 100, and have a small
daemon drop it to 70 after *N* seconds of continuous load, restoring it when load
falls. A turbo budget, in userspace, on top of the existing `power-apply`.

Same energy for long jobs — those are thermally capped regardless — and the
first three seconds of every interaction come back. Needs the inference in the
section above tested first.

### 4. Nice the things you look at *up*

`Xorg`, `xfwm4` and `plank` all run at nice **0**, competing on two cores with
whatever is compiling. Everything visible goes through them. `Nice=-5` on the
compositor and X server makes the machine slower at work in order to make it
feel faster while working — which is the correct trade for a laptop.

### 5. Focus-follows-priority

systemd already puts each app in its own cgroup scope
(`app-com.anthropic.Claude-*.scope`). `xprop -spy _NET_ACTIVE_WINDOW` → pid →
scope → raise `cpu.weight` and `io.weight` on the focused app, lower it on the
rest. On two cores, background Electron renderers competing with the foreground
one is the most-felt contention on this machine.

Blocked on one thing: only the **memory** controller is currently delegated to
those scopes. `cpu.weight` and `io.weight` do not exist there until `+cpu +io`
is enabled down the `cgroup.subtree_control` chain.

What *is* available today is `memory.min` on the focused app, so the thing you
are looking at never has its pages reclaimed to zram. With `swappiness=180`
that stutter on returning to a backgrounded window is real.

### 6. Writeback in bytes, not percent

`vm.dirty_ratio=20` of 7.8 GB is ~1.5 GB of dirty pages that can be handed, all
at once, to a disk that accepts one command at a time. `vm.dirty_bytes` around
64 MB (background 32 MB) makes a large save trickle instead of stalling the UI.

Related: `watermark_scale_factor` is the default **10**, so `kswapd` starts late
and the machine reaches *direct* reclaim — which is what a freeze is. 100–200
trades a little RAM for never getting there.

### 7. Warm the page cache for the apps you actually launch

One command at a time, ~222 MB/s, and 2.8 GB of RAM sitting free. A login- or
idle-time warm of the binaries and mapped libraries of the five apps in daily
use converts cold launches into warm ones, using memory that is otherwise idle.
`vmtouch` is not installed; a read loop over `/proc/*/maps` of the previous
session's apps does the same thing.

### 8. Remove a frame

Compositing adds a frame at 59.94 Hz — about 17 ms between input and photon.
`xfwm4`'s `vblank_mode` is `auto`; `xpresent`, `glx` and `off` are measurably
different on Intel. The macOS look needs compositing, so this is the free half of
the question.

### 9. Acknowledge input in under 150 ms

What makes a machine feel fast is that *something* happens promptly, not that
the work is finished. A launch indicator in plank or Spotlight the moment a key
is pressed covers a cold-launch wait perceptually. It is the trick macOS used on
this exact hardware. Spotlight here is ours to change.

### 10. Render fewer pixels

2304×1440 at 168 DPI on a GT2 IGP: everything is rasterized and composited at
3.3 Mpx. Dropping the Electron/browser device scale factor a notch — or driving
the panel at 1920×1440 with scaled fonts — cuts that by roughly a third, which
is the largest single lever available for UI smoothness on this GPU. It costs
sharpness. On a Retina panel there is some to spend. `bin/app-probe` can measure
it the same way Reduce motion was measured.

---

## Ordering

1, 2 and 4 are cheap, reversible, and change nothing about what the machine
computes. 3 and 5 are the interesting ones and both need building. 10 is the
heretical one and is the only item here with a real downside.

Measure interactive-length tasks, not benchmarks. A throughput number cannot see
any of this.
