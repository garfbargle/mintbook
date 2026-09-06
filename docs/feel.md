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

### 2. Fix the worst moments, not the average — **built, measured, needs one root command**

The SSD controller takes **one command at a time** (`qdepth_one`), and
`nr_requests` is **2**. A background job therefore does not *share* this disk
with the desktop. It takes it. Twelve maintenance units fire on their own timers
and do exactly that: `apt-daily`, `apt-daily-upgrade`, `plocate-updatedb`,
`man-db`, `e2scrub_all`, `fstrim`, `motd-news`, `fwupd-refresh`, `anacron`,
`logrotate`, `dpkg-db-backup`, `systemd-tmpfiles-clean`.

[`bin/quiet-timers`](../bin/quiet-timers) installs a drop-in on each one.
`--check` is read-only and needs no root; `--undo` removes them.

**What that is worth was measured, and it is not what this entry first claimed.**
The original claim — that a busy disk makes the desktop go to glue — did not
reproduce. A 512 MB write and a full metadata walk of `/` each left X round trips
essentially untouched, while I/O pressure tripled. The X server does no disk
I/O; it was the wrong probe for the question.

What a busy disk *does* cost is **application launches**.
[`bin/cold-read`](../bin/cold-read) evicts a 177 MB library and times reading it
back:

```
quiet      median   905 ms
contended  median  1668 ms      +763 ms, 1.8x, arms not overlapping
```

And cold versus cached on the same file is **881 ms against 85 ms** — a factor
of ten. All three runs, including the two that found nothing:
[2026-09-06-io-contention.md](measurements/2026-09-06-io-contention.md).

So this change is worth having, for a narrower and better-understood reason than
the one it started with: it keeps a timer from doubling the launch time of the
next thing you open.

**The obvious way to do it does not work here, and that is worth recording.**
`IOSchedulingClass=idle` is *already* set on `plocate-updatedb`, `man-db` and
`systemd-tmpfiles-clean` by their own packages — and does nothing, because
**mq-deadline implements no I/O priorities**. Only BFQ does, and BFQ is not
loaded (switching to it would reopen a scheduler question this repository
already settled by measurement). ionice is inert on this machine no matter who
sets it.

What is enforced whatever the elevator is, is blk-throttle:

```
Nice=19
CPUWeight=10
IOReadBandwidthMax=/dev/nvme0n1  32M
IOWriteBandwidthMax=/dev/nvme0n1 16M
IOSchedulingClass=idle            # inert here; kept for a scheduler that honours it
```

Setting any `IO*` property is also what makes systemd enable the `io` controller
down `cgroup.subtree_control`, which is otherwise `cpu memory pids` — the
throttle knobs do not exist until a unit asks for them.

Not yet applied: needs root, and no password is available to this session.

```bash
sudo bin/quiet-timers        # then: bin/quiet-timers --check
```

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

### 4. Nice the things you look at — **measured, built, needs one root command**

`Xorg`, `xfwm4`, `xfsettingsd`, `xfdesktop`, `xfce4-panel` and `plank` all run
at nice **0**, competing on two cores with whatever else is running. Everything
visible goes through them, so on a saturated machine the desktop is what gets
preempted: the machine is not slower, it only looks it.

[`bin/desktop-latency`](../bin/desktop-latency) measures that, by loading the
machine twice and timing X round trips under each arm:

```
idle       median  16 ms   p95  34 ms
competing  median  40 ms   p95  64 ms      load at nice 0
niced      median  27 ms   p95  41 ms      load at nice 19
```

Load costs the X server **+24 ms** of median round trip; separating priorities
returns **13 ms**, and p95 falls from 64 ms to 41 ms. Raw:
[2026-09-06-desktop-latency.md](measurements/2026-09-06-desktop-latency.md).

That measurement is a **proxy**: it nices the competitor *down*, because raising
Xorg up needs `CAP_SYS_NICE`. [`bin/desktop-nice`](../bin/desktop-nice) does it
from the other end, at nice −5, installed as a timer so it survives the logout
that restarts Xorg and the panel. `--check` is read-only; `--undo` puts
everything back to 0.

Not yet applied: needs root.

```bash
sudo install -m755 bin/desktop-nice /usr/local/sbin/mintbook-desktop-nice
sudo install -m644 config/systemd/mintbook-desktop-nice.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now mintbook-desktop-nice.timer
```

This makes the machine slower at work in order to keep it responsive while
working. That is the right trade for a laptop, and it is a trade, not a win.

### 5. Focus-follows-priority — **built, running**

systemd puts each application in its own cgroup scope.
[`bin/focus-priority`](../bin/focus-priority) follows `_NET_ACTIVE_WINDOW`,
resolves the focused window to its scope, and gives that scope `cpu.weight`
**400** against **50** for everything else, plus `memory.low` of 512 MB so the
app you are looking at is the last thing reclaimed to zram — which matters at
`swappiness=180`.

A cgroup is the right unit here. The focused window belongs to one process, but
its renderers, GPU process and helpers are all in the same scope, so weighting
the scope weights the whole application without enumerating it.

It costs nothing between windows: `xprop -spy` blocks until the focus actually
changes. There is no polling loop.

Two things had to be solved, and both are worth recording:

- **`cpu.weight` did not exist on application scopes.** The `cpu` controller is
  available to `app.slice` but was not in its `cgroup.subtree_control`, and
  systemd only enables it there when a unit *inside* `app.slice` asks for it —
  which no desktop-launched scope does. The subtree is delegated to this user,
  so the script enables it itself, idempotently. Every scope simply gains the
  default weight of 100.
- **`_NET_ACTIVE_WINDOW` returns two window ids** (`0x5400004, 0x0`). Taking the
  last field, which is the obvious thing to write, yields `0x0` and resolves
  nothing — silently, because every lookup after it just fails. The first
  version of this script did exactly that and weighted the focused app *down*.

**Its reach is smaller than it looks, and that is the honest caveat.** Only
applications launched into their own systemd scope can be weighted. On this
desktop right now there is exactly **one** such scope. Anything launched by a
route that does not create a scope lands in the session's own cgroup, where
there is nothing to separate. `bin/focus-priority --check` lists what exists.

`io.weight` is not available at all: the `io` controller is not enabled at the
system level, and `io.weight` is a BFQ feature — see the note under item 2 about
why BFQ is not on this machine.

```bash
systemctl --user enable --now mintbook-focus-priority.service   # installed and running
systemctl --user disable --now mintbook-focus-priority.service  # undo, and it clears what it set
```

Not measured: whether this changes anything a person can feel, as opposed to
changing numbers in `cpu.weight`. With one scope in play it very likely does not
yet. The measurement to make is `bin/desktop-latency`-shaped, with a real second
application competing.

### 6. Writeback in bytes, not percent — **written, unproven, needs root**

`vm.dirty_ratio` is 20% of 7.8 GB: roughly **1.5 GB** of dirty pages that can be
handed at once to a device that accepts one command at a time. `vm.dirty_bytes`
of 64 MB (background 32 MB) makes a large save trickle instead of arriving as a
wall. `watermark_scale_factor` is the default **10**, so `kswapd` starts late
and the machine can reach *direct* reclaim — which is what a freeze is; 100
trades a little held-back memory for not getting there.

Both are in [`config/sysctl.d/99-mintbook-feel.conf`](../config/sysctl.d/99-mintbook-feel.conf).

**Unproven, and the one test run argues against it.** The 512 MB write in
measurement 1 above never came close to the 1.5 GB limit and disturbed nothing,
so the stall this is meant to prevent was not reproduced. What was *not* tested
is an application launch during a large write — which, given what item 2 found,
is where the cost would actually show. That test is the one to run before
applying this.

```bash
sudo install -m644 config/sysctl.d/99-mintbook-feel.conf /etc/sysctl.d/
sudo sysctl -p /etc/sysctl.d/99-mintbook-feel.conf
# undo: rm the file, then
# sudo sysctl -w vm.dirty_ratio=20 vm.dirty_background_ratio=10 vm.watermark_scale_factor=10
```

It is a trade in the direction of smoothness over bulk write throughput, and on
a `qdepth_one` device that is probably the right direction — but "probably" is
not a measurement, and this file does not pretend otherwise.

### 7. Warm the page cache for the apps you actually launch — **built, running**

Cold and cached, for the same 177 MB library, on this disk:

```
evicted   881 ms
cached     85 ms      10x
```

There is 5.0 GB of memory available and the apps worth warming come to
**624 MB**. [`bin/warm-cache`](../bin/warm-cache) reads each app's binary, its
libraries and its install directory into the page cache, using memory that is
otherwise idle to spend nothing and remove that wait. The kernel remains free to
drop any of it under pressure, which is the correct behaviour.

Resolving an app to its files is the part that needed care: `firefox` and
`google-chrome` are wrapper scripts, and their real weight — `libxul.so` is
177 MB — is `dlopen`ed, so it appears in no `ldd` output. The script takes the
install directory's own shared objects as well.

```bash
systemctl --user enable --now mintbook-warm-cache.timer   # installed; runs 3 min after login
bin/warm-cache --check                                    # what it would read, and free memory
```

Not measured: whether a warmed Firefox actually *starts* faster, as opposed to
reading faster. Proving that needs `drop_caches`, which needs root, and a real
launch after a real boot.

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
