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

### 1. Keyboard repeat — **applied**, 500 ms / 20 Hz → 200 ms / 40 Hz

```
before   auto repeat delay:  500    repeat rate:  20
after    auto repeat delay:  200    repeat rate:  40
```

Nothing set it — the `keyboards` channel held only `/Default/Numlock`, so
`xfsettingsd` left X11's own defaults in place. Every held arrow key, every
backspace run, waited half a second and then crawled at 20 Hz.

Set through xfconf, which both applies immediately and persists across logins:

```bash
xfconf-query -c keyboards -p /Default/KeyRepeat       -n -t bool -s true
xfconf-query -c keyboards -p /Default/KeyRepeat/Delay -n -t int  -s 200
xfconf-query -c keyboards -p /Default/KeyRepeat/Rate  -n -t int  -s 40
```

Undo: set `Delay` back to 500 and `Rate` to 20, or `xfconf-query -c keyboards -p
/Default/KeyRepeat/Delay -r` to drop the properties entirely and return to the X
default. If held keys overshoot, `Rate` 30 is calmer; the delay is the half that
matters most.

**A claim in the first draft of this file was wrong and is corrected here.** It
said macOS "ships far faster" on this hardware. It does not: macOS defaults to
`InitialKeyRepeat` 25 (≈375 ms) and `KeyRepeat` 6 (≈90 ms, ≈11 Hz) — a *slower*
repeat rate than X11's 20 Hz, with a shorter delay. The case for this change is
not that macOS is quicker. It is that both defaults are conservative, the delay
is the part a person feels, and 200 ms is where a held key stops feeling like a
request and starts feeling like a control. The macOS-power-user equivalent is
roughly 225 ms / 33 Hz, which is close to what is set here.

This changes no work the machine does. It was the highest felt value per minute
of effort on the list, and it is done.

### 2. Fix the worst moments, not the average — **built, needs one root command**

The SSD controller takes **one command at a time** (`qdepth_one`), and
`nr_requests` is **2**. A background job therefore does not *share* this disk
with the desktop. It takes it. Twelve maintenance units fire on their own
timers and do exactly that: `apt-daily`, `apt-daily-upgrade`,
`plocate-updatedb`, `man-db`, `e2scrub_all`, `fstrim`, `motd-news`,
`fwupd-refresh`, `anacron`, `logrotate`, `dpkg-db-backup`,
`systemd-tmpfiles-clean`.

These move no average. They are the "why is it frozen" minutes, and those are
what a person remembers. `io` PSI `some avg10` was **3.49** while this was being
written — the machine is already waiting on that disk.

[`bin/quiet-timers`](../bin/quiet-timers) installs a drop-in on each one.
`--check` is read-only and needs no root; `--undo` removes them.

**The obvious fix does not work here, and that is worth recording.**
`IOSchedulingClass=idle` is *already* set on `plocate-updatedb`, `man-db` and
`systemd-tmpfiles-clean` by their packages — and it does nothing, because
**mq-deadline does not implement I/O priorities**. Only BFQ does, and BFQ is not
loaded (and switching to it would reopen a scheduler question this repository
already settled by measurement). So ionice is inert on this machine no matter
who sets it.

What is enforced regardless of elevator is blk-throttle, at the block layer:

```
Nice=19
CPUWeight=10
IOReadBandwidthMax=/dev/nvme0n1  32M
IOWriteBandwidthMax=/dev/nvme0n1 16M
IOSchedulingClass=idle            # inert here; kept for a scheduler that honours it
```

Setting any `IO*` property is also what makes systemd enable the `io` controller
down `cgroup.subtree_control`, which is currently `cpu memory pids` — so the
throttle knobs do not exist until a unit asks for them.

Not yet applied: this needs root and no password is available to this session.

```bash
sudo bin/quiet-timers        # then: bin/quiet-timers --check
```

Untested claim, stated as one: the caps are chosen to leave the desktop most of
a ~222 MB/s device, not measured against a timer actually running. The honest
test is to run `plocate-updatedb` by hand with and without the drop-in and watch
`io` PSI, which nobody has done yet.

### 3. Cap the sustained, not the burst — **measured, built, running**

The inference above is now a measurement. [`bin/burst-probe`](../bin/burst-probe)
times a fixed ~1 s single-core task under each cap, interleaved, and prints the
spread inside each arm:

```
uncapped (100)  n=5  mean 661 ms   min 589  max 744   spread 155 ms
capped   (70)   n=5  mean 903 ms   min 839  max 967   spread 128 ms

cap costs +241 ms on ~1 s of work (+36.5%)
```

**The arms do not overlap.** The slowest uncapped run is faster than the fastest
capped one, and package temperature (72–80 C) did not sort with the arms. Raw
numbers: [2026-09-06-burst-cap.md](measurements/2026-09-06-burst-cap.md).

So both of these are true, and they are not in conflict:

| length of work | faster | source |
|---|---|---|
| ~1 second | **uncapped**, by 36.5% | this measurement |
| sustained | **capped** — 75 does 20–25% more work than 100 | [hardware.md](hardware.md) |

An uncapped chassis sprints into the 95 C wall and then eats throttle stalls.
A capped one never gets the sprint. [`bin/turbo-budget`](../bin/turbo-budget)
takes both: while a cap is in force it grants **8 uncapped seconds** at the
start of any burst, then hands the cap back and keeps it until the machine goes
quiet. A click gets the whole chip; a compile gets the cap it was always going
to get.

Verified live, on a forced `power-saver` baseline:

```
t= 1.0s  cap=70          quiet
t= 1.5s  cap=100         burst detected
t= 8.5s  cap=100         still inside the budget
t= 9.0s  cap=70          budget spent — cap back, under continuing load
```

It needs no root: it writes a profile name to `/run/mintbook-power/want`, the
password-free channel the panel already uses, and it stands down entirely
whenever nothing is capped — so picking Balanced by hand switches it off.

**Its own cost, because this repository has been bitten there before:** under
10 ms of CPU in 29 s of running. The loop forks nothing — `/proc` through the
`read` builtin, time from `EPOCHREALTIME`, arithmetic in bash, and the sleep is
a `read` timeout on a fifo nobody writes to. The most expensive software ever
found on this machine was a panel plugin that forked a Python interpreter twice
a tick.

```bash
systemctl --user enable --now mintbook-turbo-budget.service   # installed and running
systemctl --user disable --now mintbook-turbo-budget.service  # undo
```

Tunable through the environment: `BUDGET` (8 s), `TRIGGER` (25% of total CPU),
`QUIET` (10%), `MINGAP` (3 s between requests).

Not measured: what the extra 8-second sprints cost in battery life or in
temperature over a real session. The sprints are short and the chassis was
already reaching 95 C under any sustained load, but that is an argument, not a
number.

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
