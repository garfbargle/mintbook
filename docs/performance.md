# Performance — what was changed, and what it was worth

A pass over this machine on **2026-09-04**, looking for work it was doing that
it did not need to do. Everything below was measured on the machine, not
reasoned about. Where a measurement turned out to be confounded, that is
recorded too, because it happened three times.

MacBook8,1 · fanless Core M-5Y31 · 2 cores / 4 threads · 7.7 GB · Mint 22.3 · kernel 7.0

---

## Gains

### 1. CPU mitigations off — syscalls 5.7x faster

```
raw getpid syscall    720 ns  ->  127 ns
```

The single largest change. Pinned to one core, same binary, comparable load
either side. `/sys/devices/system/cpu/vulnerabilities/` goes from 9 mitigated to
1. This is a **security posture decision**, not a free win — the reasoning, the
threat model it accepts, and the one-line undo are in
[hardware.md](hardware.md#cpu-mitigations--your-call-with-a-number).

Knock-on, indicative only: `python3 -c pass` 50 ms → 31 ms. Disk throughput
unchanged at ~222 MB/s, which is the control — it is not syscall-bound and did
not move.

### 2. The status bar — 20.4% → 5.6% of one core

The most expensive software on the machine was the thing drawing six glyphs in
the top bar. Measured from `cutime` on the genmon wrappers: **800 seconds of CPU
in a 1 h 55 m session.**

Interleaved A/B, old scripts against new, same load, same machine:

| plugin | before | after | |
|---|---|---|---|
| `panel-power` | 357 ms | **33 ms** | 10.8x |
| `panel-bt` | 219 ms | **31 ms** | 7.1x |
| `panel-cpu` | 83 ms | **78 ms** | 1.1x |

At the unchanged poll periods: **20.4% → 5.6% of one core.**

Neither cause was the poll period:

- `panel-power` started a Python interpreter in order to fork a *second* Python
  interpreter — `powerprofilesctl` is itself Python. Now bash + `busctl`.
- `panel-bt` spent 190 ms of 197 ms importing `gi.repository` to make one D-Bus
  call. Now bash + `dbus-send`, parsed with awk, verified against six fixtures.
- `panel-cpu` must stay Python — it renders the SVG — so its `/proc` walk moved
  to every third tick instead. A modest win, and reported as one.

Periods were deliberately left alone. See
[desktop.md](desktop.md#what-the-bar-costs-2026-09-04).

### 3. The battery CPU cap was never being applied

`power-check` said `MISMATCH`: on battery, profile `power-saver` but
`max_perf_pct=100` instead of 70. The machine had been running uncapped, at
86–90 °C, on every boot.

The unit worked. thermald reset it 40 seconds later — and `After=power-profiles-daemon.service`
never bound, because PPD is D-Bus-activated and started 45 s *after* the unit
ordered behind it. Fixed with `--reassert` plus a settle timer at
`OnBootSec=90`, and thermald masked. Confirmed through a real reboot.

### 4. i965 was never reaching a single application

`/etc/environment.d/90-mintbook-libva.conf` had been installed and inert.
`environment.d` is read by `systemd --user`; the desktop is
`lightdm → Xsession → xfce4-session`. Chrome, Cursor and Claude Desktop all had
`iHD_drv_video` mapped. Logging out would never have fixed it. Now forced from
`/etc/X11/Xsession.d/56mintbook-libva`, confirmed by the mapped library.

### 5. Nine services and two autostart entries

Each behind a probe, in [`bin/service-trim`](../bin/service-trim): ModemManager,
`cups` ×4, switcheroo-control, casper ×2, rsyslog, kerneloops. Plus
`print-applet` (35 MB of Python watching a print queue that does not exist) and
`geoclue-demo-agent`.

---

## Six things that were wrong

Four proposed tunings and two claims about how the machine works, all withdrawn
after being checked. They are kept here because each one is an idea a reasonable
person would have again.

| Claimed | Actually |
|---|---|
| `mq-deadline` on an NVMe is wrong, use `none` | Apple S1X carries the `qdepth_one` quirk — **one command in flight, ever**. The scheduler was merging away 23% of reads and 54% of writes. `none` would have handed that back |
| `read_ahead_kb` 256 should beat 128 | Measured across 64–1024: sequential is flat and non-monotonic (noise), and random 4K only gets *worse* above 256. Nothing to win |
| `snd_hda power_save=0` is an oversight | Deliberate and load-bearing. The CS4208 amp rails are set once by EFI; a D3 cycle kills the speakers until reboot. `doctor` now **fails** if it ever changes |
| No `i915` tuning is set | It is set to `-1` = *"use per-chip default"*. Forcing `enable_fbc=1` overrides a per-chip decision, it does not switch on something that was off |
| `environment.d` needs a logout to apply | Nothing in the desktop reads it. A logout would never have helped |
| OpenCore is the picker, so `/etc/default/grub` does nothing | OpenLinuxBoot autodetects and reads `GRUB_CMDLINE_LINUX_DEFAULT` directly. It is how `intel_iommu=off` got there |

And a bug in the tooling written during the pass: `systemctl is-enabled X | grep -q masked`
is wrong under `set -o pipefail`, because `is-enabled` exits non-zero for a
masked unit *while printing* `masked`. It made `power-check` report a masked
thermald as "not running".

---

## Measure it, and then measure it properly

A straight before/after flattered a change **three times** in one session, on a
machine with a live desktop and browsers.

1. **The genmon rewrite** read 11.6% → 7.8%, understating it, because the second
   window was ~1.8x busier. The three plugins that were *not* touched proved it
   by rising too — `panel-night` 0.41% → 0.94% on unchanged code.
2. **`idle-probe --try`** reported a management-engine mailbox "saving" 1.38 W of
   a 3.43 W package. 0.86 W of that came out of **core** and 0.47 W out of
   **dram**. A mailbox cannot do that.
3. A third window later read 7.35%, again not comparable to either.

The fix in both tools is the same: **interleave the arms and print the noise
floor.** `idle-probe --try` now alternates `on`/`auto` for `--cycles` pairs and
says *not measurable* when the difference is inside a single arm's spread. The
panel numbers above come from an interleaved A/B of old and new scripts under
one load.

If a control that should not have moved did move, the measurement is of the
machine's mood, not of the change.

---

## Tools

All read-only unless stated. `--check` / no-argument forms need no root.

| | |
|---|---|
| [`bin/doctor`](../bin/doctor) | 52 checks. Everything installed, plus guards on the things that would fail silently |
| [`bin/io-probe`](../bin/io-probe) | Disk constraints and cold-cache benchmark. `--sweep` walks `read_ahead_kb` and restores it |
| [`bin/idle-probe`](../bin/idle-probe) | RAPL watts, FBC/PSR state, runtime PM. `--try` A/Bs one device and puts it back |
| [`bin/service-trim`](../bin/service-trim) | `--check` re-runs every probe and says what it would mask, and why |
| [`bin/power-check`](../bin/power-check) | Live CPU policy against what it should be |

---

## Closed by measurement

- **PCI runtime PM.** Measured on battery: letting the MEI controller suspend
  saved **under 0.07 W** — below what a four-minute, 240-sample run could
  resolve, on a 6 W machine. The device really did enter D3. The remaining
  `control=on` devices are on-chip controllers of the same order, and five of
  them are Wi-Fi, the camera, the NVMe, the Bluetooth UART and applespi, which
  is most of this repo's scar tissue. Not worth the risk for an effect too small
  to find.

  The run doubled as the best demonstration of why the arms are interleaved:
  the machine drifted 0.54 W over four minutes while the effect under test was
  0.04 W — **14x the signal** — and a naive before/after would have reported
  ~0.20 W of savings that was purely drift. See
  [hardware.md](hardware.md#result-mei-runtime-pm-measured-2026-09-04).

## Still open

- **`i915.enable_fbc`.** Whether FBC is actually on is a root-only debugfs read.
  Change it only if it is off *and* a measurement says it is worth something.
