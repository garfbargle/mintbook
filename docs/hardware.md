# Hardware status

> Summary of the 2026-09-04 tuning pass, with the numbers and the
> retractions: [performance.md](performance.md).

What works, what does not, and what was measured. Regenerate the live parts with
[`bin/hw-report`](../bin/hw-report).

| | |
|---|---|
| Model | **MacBook8,1** — MacBook (Retina, 12-inch, Early 2015), `Mac-BE0E8AC46FE800CC` |
| Chassis | Apple **A1534** (shared with MacBook9,1 and 10,1 — relevant to [audio.md](audio.md)) |
| CPU | Intel **Core M-5Y31** @ 0.9GHz base / 2.4GHz turbo — 2 cores, 4 threads, **fanless** |
| GPU | Intel HD Graphics 5300 |
| RAM | 7.7 GB — **zram swap** (half of RAM, zstd) |
| Storage | 233.8 GB NVMe |
| Display | eDP-1, 2304x1440 in 259x162mm — **~226 DPI** |
| Audio controller | PCI `00:1b.0` (Wildcat Point-LP), codec Cirrus **CS4208** |
| Wireless | Broadcom **BCM4350** (`brcmfmac`) |

## Status matrix

| Device | State | Notes |
|---|---|---|
| Display / HiDPI | **Working** | Needs manual scaling, see [display.md](display.md) |
| Wi-Fi | **Working** | `brcmfmac`, associates and resolves normally |
| **Bluetooth** | **Working on 7.0** | SSDC hidden via DSDT override on the 7.0 initrd — [bluetooth.md](bluetooth.md) |
| Internal speakers | **Working on 7.0** | [audio.md](audio.md) — CS4208 TDM, clock latch fix |
| Headphone jack | **Working** | The analog path in the codec is healthy |
| Microphone | Working | `Mic=0x18`, `Internal Mic=0x19` |
| Keyboard / trackpad | **Working** | DMA blacklist + DWT quirk; log out once for DWT — [input.md](input.md) |
| Keyboard backlight | **Working** | `spi::kbd_backlight`, hardware keys work |
| Battery | Working | ~84% of design capacity; 149 cycles |
| Power policy | **Working** | battery: `power-saver` + `max_perf_pct=70`; AC: `balanced` + full turbo — see Thermals |
| Webcam | **Working on 7.0** | FaceTime HD `14e4:1570`, 848×588; `intel_iommu=off`; one client at a time — [camera.md](camera.md) |
| VA-API | **i965** | Broadwell driver forced; iHD has no encode. No VP9/AV1 in hardware |
| Swap | **zram + sysctls** | zstd, half of RAM, `swappiness=180` `page-cluster=0` |
| Secure Boot | Not supported | Unsigned DKMS modules load without signing |

## Bluetooth is hidden by SSDC, not missing

The BCM4350 UART (`00:15.5`) has two ACPI serdev slaves. Linux binds
`URT0.SSDC` (SSD debug) first; the real `URT0.BLTH` (`BCM2E7C`) never gets a
device unless SSDC is hidden.

**Working on 7.0** after a DSDT override prepended to the initrd —
[bluetooth.md](bluetooth.md). `serial0-0` is `URT0.BLTH` / `hci_uart_bcm`,
`hci0` is **BCM4350C0**.

## Battery

| | |
|---|---|
| Health | **~84%** of design (33.7 Wh of 40.3 Wh, 2026-09-01 evening) |
| Cycles | 149 (2026-09-01) |

Good for a machine of this age. Read it with:

```bash
upower -i /org/freedesktop/UPower/devices/battery_BAT0
```

> UPower's `percentage:` is the charge relative to the battery's **present usable
> capacity**; its `capacity:` field is battery health relative to the original
> design. On this Mac, the kernel's raw `/sys/class/power_supply/BAT0/capacity`
> behaves like charge relative to the original design capacity, so mintbook
> normalizes `charge_now / charge_full` for its user-facing percentage.

**Discharge** (earlier 2026-09-01): around **10–14 W** (~2.5 h at ~77% charge).
**Charge** (same evening, ~52%): `energy-rate` 7–19 W (spikes ~16–19 W). Charging
heats the chassis on its own.

This session did not unplug, so discharge was not re-measured. Package RAPL under
Cursor+Chrome on AC is the before/after below (~7 W unrestricted → ~5.8 W at
`max_perf_pct=70`). Display + Wi-Fi + the rest of the board sit on top of that.

## Thermals

The CPU is fanless and thermally limited — it throttles at **95 °C** (`high`/`crit`
are both 95) rather than spinning up a fan. **Policy is in place** as of 2026-09-01
(see below). Do not stack TLP or `auto-cpufreq` on top of `power-profiles-daemon`.

```bash
sensors                  # lm-sensors is installed
bin/power-check          # AC vs battery policy (read-only)
bin/hw-report            # includes profile, EPB, max_perf_pct
```

### What the hardware is doing

| | |
|---|---|
| `power-profiles-daemon` | 0.21, active. Driver `intel_pstate`, platform `placeholder` |
| `intel_pstate` | **passive** → `intel_cpufreq` + `schedutil`. No EPP sysfs (Broadwell has no HWP) |
| EPB | `/sys/devices/system/cpu/cpu*/power/energy_perf_bias` — this is what PPD actually writes |
| RAPL PL1 | firmware default **~46–49 W** on a **4.5 W TDP** chip. Writes stick since thermald was masked, but do not bind as expected — see Ruled out |
| `thermald` | **masked** since 2026-09-04: no sensors here, and it reset the cap. The 95 °C backstop is the CPU's own TCC — see below |
| GPU | HD 5300, RC6 on, RPS 300–850 MHz. Already idling at RPn when the GT is quiet |
| Backlight | `acpi_video0` at **20/100**. Keyboard backlight is `spi::kbd_backlight` (0 when last applied) |
| Wi-Fi | NetworkManager `wifi.powersave = 3` already |

Idle has been ~60 °C (quiet desktop, earlier). This session’s load was Cursor + Chrome
on AC, which is the real desktop workload.

### Baseline (before policy, Cursor+Chrome, AC, charging)

| | Package | RAPL package | avg MHz |
|---|---|---|---|
| `balanced` (EPB=6) | **82–93 °C** | 6.89 W | 2000 |
| `power-saver` alone (EPB=15) | **83–93 °C** | (same 2.0 GHz) | 2000 |

`powerprofilesctl set power-saver` **does** set EPB from 6 → 15. It does **not**
change `no_turbo`, `max_perf_pct`, or `scaling_max_freq`. Under Electron the cores
stay at 2.0 GHz all-core turbo until 95 °C. Profile-only is not a thermal policy
on this chip.

### Levers that were measured

| Lever | Package | RAPL | avg MHz | Keep? |
|---|---|---|---|---|
| `max_perf_pct=70` | **77 °C** | 5.76 W | 1595 | **yes — battery** |
| `max_perf_pct=50` | 76 °C | 5.83 W | 1200 | no extra win |
| `no_turbo=1` | 75–76 °C | 5.43–5.53 W | 900 | works; slower than 70% for ~0.2 W |
| RAPL PL1 5–7 W | 84–90 °C | 6.5–7.7 W | 2000 | **no** — see ruled out |

After install, on AC (intended: full turbo): package **83 °C**, 2.0 GHz,
`balanced` / EPB=6 / `max_perf_pct=100`. Matches the unrestricted baseline.

### max_perf_pct on AC under sustained load (2026-09-03)

Measured with [`bin/thermal-sweep`](../bin/thermal-sweep) — 4 all-core awk workers,
60 s soak per step, 30 s sample, temp/MHz averaged across the window. The sweep runs
**down and back up** because the desktop load drifts; if the two `100` rows disagree
the run is contaminated and the middle rows mean nothing. They agreed on both runs.

| `max_perf_pct` | pkg °C | skin (TC0P) °C | RAPL W | avg MHz | **work/s** |
|---|---|---|---|---|---|
| 100 | 89.6 / 90.6 / 90.4 / 90.2 | 66–67 | 7.1–7.5 | 1728–1950 | **2.43–2.80** |
| 85 | 90.2 / 90.7 | 66 | 7.5–8.1 | 1819–1931 | 2.80–2.83 |
| 75 | 89.8 / 90.1 / 90.4 | 66–67 | 7.3–7.6 | 1717–1789 | **3.13–3.33** |

Two results, and the second one was not expected:

**A cap does not cool this machine under sustained load.** Every step sits at ~90 °C
and ~7.4 W. The chassis is power-saturated either way and thermald holds the budget
constant, so the heat is the same whatever the ceiling says. The battery win recorded
above (`max_perf_pct=70` → 77 °C) came under *bursty* Cursor+Chrome load, where the
cap prevents sprints. It does not transfer to a saturated all-core load.

**Capping to 75 does ~20–25% more work for the same heat.** Six samples, clean
separation, no overlap. At 100 the chip sprints at the thermal wall and eats hard
throttle stalls; at 75 it holds ~1.75 GHz and finishes more chunks. `avg MHz` is
*higher* at 100 while work is lower — the reported frequency is hiding stalled
execution, which is why this table has a work column and the ones above do not.

> **Scope check, September 10:** that result belongs to the four-worker awk
> workload. A [two-worker source-compilation comparison](measurements/2026-09-10-workload.md)
> found medians of 3.019 corpus passes/s on Balanced and 2.993 on Sustained,
> with overlapping runs and the same 94.4 C mean temperature. Long work does
> not universally benefit from the cap; power defaults were left unchanged.

This is a real trade-off, not a free win: the sprint is useful for short interactive
bursts (app launch, page render) that finish before they hit the wall. A blanket AC
cap would trade that away to speed up long compiles, so it is **not the default** —
see Ruled out. It is on the panel instead, as **Sustained**, for when you know the
job is long. Auto still reclaims it on the next charger event.

### The three profiles

`powerprofilesctl` supplies EPB; `max_perf_pct` is ours. Measured on battery
2026-09-04 through the panel's own request-file path:

| Panel | PPD profile | EPB | `max_perf_pct` | For |
|---|---|---|---|---|
| Power Saver | `power-saver` | 15 | 70 | battery default — coolest, ~1.6 GHz |
| Balanced | `balanced` | 8 | 100 | AC default — short bursts finish before the wall |
| **Sustained** | `performance` | 0 | **75** | long jobs — ~20–25% more work, same heat |

**"Performance" used to mean EPB=0 and `max_perf_pct=100`, and that was a placebo
pointing the wrong way.** It differed from Balanced only in EPB, and 100 is the
*worst* ceiling for sustained work on this chassis (see the sweep above). Renamed to
**Sustained** and repointed at 75 on 2026-09-04, which is the setting that actually
gets more done. The PPD key is still `performance`, so the icon filenames and
`powerprofilesctl get` parsing are unchanged.

> Recorded EPB for `balanced` was 6; it read **8** when re-measured on battery
> 2026-09-04. Both are PPD's number, not ours. Do not treat 6 as a constant.

### Policy (installed)

On **battery**: `power-saver` (EPB=15) and `intel_pstate` `max_perf_pct=70`
(~1.6 GHz ceiling). On **AC**: `balanced` (EPB=6) and `max_perf_pct=100`.

```
pkexec /home/cobo/mintbook/bin/power-install
```

That copies:

- [`bin/power-apply`](../bin/power-apply) → `/usr/local/sbin/mintbook-power-apply`
- [`config/udev/99-mintbook-power.rules`](../config/udev/99-mintbook-power.rules)
  → `/etc/udev/rules.d/` (ADP1 `change` → `SYSTEMD_WANTS`)
- [`config/systemd/mintbook-power.service`](../config/systemd/mintbook-power.service)
  → `/etc/systemd/system/` (oneshot at boot; udev runs it again on unplug/plug)
- [`config/systemd/mintbook-power-request.path`](../config/systemd/mintbook-power-request.path)
  + [`.service`](../config/systemd/mintbook-power-request.service) — panel writes
  `/run/mintbook-power/want`, root applies it. **No password on click.** Until
  2026-09-11 `bin/turbo-budget` wrote the same file on battery, and a
  `mode=balanced`/`mode=power-saver` flip every few seconds in
  `journalctl -t mintbook-power` was that, not clicks. Its replacement,
  [`bin/input-boost`](../bin/input-boost), writes `max_perf_pct` directly and
  never touches this file. See [feel.md](feel.md), item 3.
- [`config/systemd/mintbook-power-settle.timer`](../config/systemd/mintbook-power-settle.timer)
  + [`.service`](../config/systemd/mintbook-power-settle.service) — re-applies the
  cap 90 s after boot, once thermald and PPD have started. See below.
- [`config/tmpfiles.d/mintbook-power.conf`](../config/tmpfiles.d/mintbook-power.conf)
  → `/etc/tmpfiles.d/` (`/run/mintbook-power` owned by root and the invoking
  desktop user's primary group, mode 0770; and `max_perf_pct` made writable by
  that group, so [`bin/input-boost`](../bin/input-boost) can lift the cap with
  no root helper in the path)
- [`config/polkit/org.mintbook.power.policy`](../config/polkit/org.mintbook.power.policy)
  + [`10-mintbook-power.rules`](../config/polkit/10-mintbook-power.rules) — leftover
  `pkexec` from a terminal, not used by the panel

The **panel icon** (genmon, left of the battery) is the switcher. XFCE Power
Manager settings has no power-profiles UI in 4.18. Click the gauge icon for
Power Saver / Balanced / **Sustained**. Plug or unplug still reapplies auto. CLI
from a root shell: `mintbook-power-apply <profile>`. The panel does **not**
call `pkexec` — a genmon-spawned pkexec still asked for a password even with
`allow_active=yes`.

Confirmed 2026-09-01: `udevadm test --action=change` on ADP1 sets
`SYSTEMD_WANTS=mintbook-power.service`; journal
`mintbook-power: ac=1 profile=balanced max_perf_pct=100 epb=6`.

```bash
bin/power-check
```

Undo:

```bash
sudo systemctl disable --now mintbook-power.service mintbook-power-request.path \
       mintbook-power-settle.timer
sudo rm -f /usr/local/sbin/mintbook-power-apply \
           /etc/udev/rules.d/99-mintbook-power.rules \
           /etc/systemd/system/mintbook-power.service \
           /etc/systemd/system/mintbook-power-request.path \
           /etc/systemd/system/mintbook-power-request.service \
           /etc/systemd/system/mintbook-power-settle.timer \
           /etc/systemd/system/mintbook-power-settle.service \
           /etc/tmpfiles.d/mintbook-power.conf \
           /usr/share/polkit-1/actions/org.mintbook.power.policy \
           /etc/polkit-1/rules.d/10-mintbook-power.rules
echo 100 | sudo tee /sys/devices/system/cpu/intel_pstate/max_perf_pct
powerprofilesctl set balanced
```

### The cap did not stay put (2026-09-04)

`bin/power-check` reported `MISMATCH`: on battery, PPD `power-saver` — correct —
but `max_perf_pct=100` instead of 70. The machine had been running uncapped on
battery, at 86–90 °C, for the whole session.

The unit had done its job. The journal for that boot:

```
18:42:23  mintbook-power   mode=auto ac=0 profile=power-saver max_perf_pct=70
18:43:01  thermald         started
18:43:08  power-profiles-daemon  started
```

It set 70 and something reset it 40-odd seconds later. `mintbook-power.service`
carries `After=power-profiles-daemon.service`, and it did not hold. **Corrected
2026-09-11:** this section used to say that was because PPD is D-Bus-activated
and starts when something first asks for it. It is not: PPD has been enabled
for `graphical.target` since 2026-08-30, and systemd starts it at boot right
after `multi-user.target`. The `After=` did not hold because it made an ordering
cycle, and systemd threw away the unit's boot job. See
[The unit never ran at boot](#the-unit-never-ran-at-boot-2026-09-11). That
boot's journal has since rotated, so what triggered the 18:42:23 run cannot be
rechecked. The thermald finding below stands either way.

thermald is the one that writes it (`strings /usr/sbin/thermald` has
`/max_perf_pct`), and on this machine it is doing so with no idea what the
temperature is:

```
NO RAPL sysfs present
Thermal DTS: No coretemp sysfs found
Thermal DTS or hwmon: No Zones present Need to configure manually
Config file /etc/thermald/thermal-conf.xml does not exist
```

No zones, no sensors, no DPTF tables, in `--adaptive` mode. It manages nothing
and can only fight the policy, so `bin/tune-install` now masks it. The thermal
backstop was never thermald — it is the CPU's own TCC throttle, in silicon,
which is what `package_throttle_count` counts (4116 events, 18.6 s, in the first
two hours of that boot).

Two fixes, because masking thermald alone would leave the same hole open for the
next daemon that decides it owns `max_perf_pct`:

- `mintbook-power-apply --reassert` re-applies the cap belonging to whatever
  profile PPD **currently** reports. It does not touch the profile, so a
  Sustained picked by hand survives it.
- `mintbook-power-settle.timer` runs that once at `OnBootSec=90`.

`bin/doctor` now tells the two cases apart. A profile picked by hand moves the
profile *and* the cap, because `power-menu` writes both — so a profile that
still matches auto while the cap does not is not a preference, it is this fault,
and doctor fails on it rather than shrugging it off as an override.

### The unit never ran at boot (2026-09-11)

The boot journal carried this on every boot:

```
multi-user.target: Found ordering cycle on mintbook-power.service/start
multi-user.target: Found dependency on power-profiles-daemon.service/start
multi-user.target: Found dependency on multi-user.target/start
multi-user.target: Job mintbook-power.service/start deleted to break ordering cycle starting with multi-user.target/start
```

The loop has three edges, and two of them are ours:

- `mintbook-power.service` has `After=power-profiles-daemon.service` (ours).
- Ubuntu's stock `/usr/lib/systemd/system/power-profiles-daemon.service` has
  `After=multi-user.target display-manager.target` and is enabled for
  `graphical.target`. This one is not ours.
- `WantedBy=multi-user.target` gives the unit an implicit
  `Before=multi-user.target` (ours).

systemd breaks the loop by deleting the mintbook-power job, so the policy was
never applied at boot. The journal keeps 12 boots (2026-09-10 21:45 to
2026-09-11 10:52), and in none of them did the unit start before 36 s. Every
run in them came from udev on a charger change, or from the settle timer and
`power-install`. Eight of those boots logged the cycle. The other four (−11,
−10, −9, −3) also lack PID 1's "Queued start job for default target" line,
which sits right after the cycle lines. So those boots lost PID 1's earliest
messages: they show a logging gap, not a boot without the cycle.

Fix: `WantedBy=graphical.target`. PPD hangs off the same target, so the order
becomes `multi-user.target` → PPD → mintbook-power → `graphical.target`, with no
loop. This is the default target here. Booting into plain `multi-user.target`
would skip the unit, but PPD would not start either, and udev plus the settle
timer still apply the cap.

Why not the other fix: dropping `After=power-profiles-daemon.service` and
keeping `multi-user.target` would not work. `mintbook-power-apply` calls
`powerprofilesctl`, which D-Bus-activates PPD. PPD is ordered after
`multi-user.target`, which in turn waits for this oneshot, so the unit would
block until the D-Bus call timed out. This follows from the unit ordering and
was not tried.

`bin/power-install` now runs `systemctl reenable` instead of `enable`. `enable`
adds the new `graphical.target.wants` link but leaves the old
`multi-user.target.wants` link in place, and that old link alone keeps the
cycle. Checked with the fixed unit in a scratch dir before installing.

How to check it without a reboot, and one check that does not work:

- `systemd-analyze verify /etc/systemd/system/mintbook-power.service` reports
  **nothing** even with the cycle present. It never builds the
  `multi-user.target` transaction.
- `systemd-analyze verify multi-user.target` (or `graphical.target`) does
  reproduce the four journal lines. After the fix, both are clean.

Confirmed through a real reboot (2026-09-11 11:22). `journalctl -b` has no
`ordering cycle` line, and
`journalctl -b -u mintbook-power.service -o short-monotonic` shows the unit
starting at 9.46 s and applying `ac=1 profile=balanced max_perf_pct=100`. That
is the first boot in the retained journal where it ran at boot.

### Ruled out

- **A blanket `max_perf_pct` cap on AC.** Measured 2026-09-03 (above). It buys
  **no** temperature and **no** watts under sustained load — the chassis is
  power-saturated at ~90 °C / ~7.4 W from 75 through 100. It would only change
  bursty behaviour, and there it costs responsiveness. If you want the throughput
  win for a long compile, set it for that compile
  (`mintbook-power-apply` from a root shell), do not make it the default.
- **`power-saver` as the only change.** EPB=15, still 2.0 GHz, still 83–93 °C.
- **RAPL PL1 as a persistent cap.** `constraint_0_power_limit_uw` accepts 5–7 W
  then returns to 24.5 W / 49 W within ~25 s (thermald and/or this Mac’s RAPL
  firmware). Package power and clocks did not follow the write.
  **Retested 2026-09-11 with thermald masked: the write now sticks** (4.5 W
  held for all 90 s), so thermald was what reset it. It still does not behave
  like a usable limit. Uncapped, with two busy threads, the package stayed at
  7.4–7.9 W / 1600–1800 MHz / 95 °C for ~75 s after the write, against a 28 s
  time window, then fell to 4.8 W / ~700 MHz / 80 °C. That is one run, and
  neither the delay nor the undershoot is explained. It stays ruled out as a cap,
  but no longer for the reason first given.
- **`no_turbo=1` as the battery default.** It works (75 °C, 5.5 W, 900 MHz) but
  `max_perf_pct=70` matches the thermals with ~1.6 GHz left. Use `no_turbo` only
  if 70% is still too hot.
- **TLP / `auto-cpufreq`.** Not installed. Do not stack on PPD.
- **picom / extra compositor.** Declined earlier; would cost GPU power. There is
  no picom.
- **Kernel cmdline / `intel_pstate=active` / i915 `enable_psr`.** No evidence they
  are required; `intel_iommu=off` stays (camera). OpenCore, not GRUB.
- **Wi-Fi powersave.** Already `wifi.powersave = 3` via NetworkManager.
- **HDA `power_save`.** Left at 0 — CS4208 speakers are fragile; see [audio.md](audio.md).
- **Lid-on-AC / sleep.** Adjacent to drain, not this session. Lid-on-battery is
  already suspend. Hibernate is impossible (zram).
- **Gtk.Menu as the panel click.** genmon starts the command with
  `g_spawn_command_line_async`, so there is no Gdk event. xfwm4 rejects a menu
  grab at time 0; the process sat in `Gtk.main()` with nothing on screen. The
  click is an override-redirect window instead (`bin/power-menu`).
- **pkexec from the panel.** `allow_active=yes` still produced a password
  dialog: a genmon-spawned process is not a polkit "active" session, so pkexec
  falls through to the default exec action. The panel writes
  `/run/mintbook-power/want`; a root path unit applies it.

## Swap (zram)

7.7 GB with Electron apps is a real OOM risk with no swap at all. Disk swap would
wear the NVMe, so this is compressed RAM instead.

**Installed 2026-09-01** via `systemd-zram-generator` (not `zram-config` — that
package is a SysV script that sizes zram to 100% of RAM). Config lives in
[`config/systemd/zram-generator.conf`](../config/systemd/zram-generator.conf)
and is copied to `/etc/systemd/zram-generator.conf`:

```
[zram0]
zram-size = ram / 2
compression-algorithm = zstd
```

Half of RAM as the uncompressed zram disk; zstd is built into this kernel
(`CONFIG_ZRAM_BACKEND_ZSTD`). Typical compression is ~2×, so a full 4 GB of
swap costs roughly 2 GB of RAM.

```bash
sudo apt install systemd-zram-generator
sudo cp config/systemd/zram-generator.conf /etc/systemd/zram-generator.conf
sudo systemctl daemon-reload
sudo systemctl start systemd-zram-setup@zram0
sudo systemctl start dev-zram0.swap
```

The setup unit only formats `/dev/zram0`. `dev-zram0.swap` is the generated unit
that actually calls `swapon`. Both come back on boot via `swap.target`.

### The sysctl half (2026-09-03)

Creating the device is only half of it. The stock VM tunables are spinning-disk
defaults and left zram nearly unused — **2.4 GB in use and 8 KB on a 3.8 GB zram
device**. [`config/sysctl.d/99-mintbook-zram.conf`](../config/sysctl.d/99-mintbook-zram.conf),
installed by [`bin/tune-install`](../bin/tune-install):

| | stock | set | why |
|---|---|---|---|
| `vm.swappiness` | 60 | **180** | swapping into RAM costs a compress, not a seek — push pages out *before* the OOM killer, which is the reason zram is here |
| `vm.page-cluster` | 3 | **0** | zram is random-access; faulting in 8 pages to use 1 is 7 wasted decompressions |
| `vm.vfs_cache_pressure` | 100 | **50** | keep dentries/inodes; this machine re-walks a lot of small files and has no disk swap to fall back on |

These only bite under memory pressure — `swapon --show` will still read ~0 used on a
quiet desktop. That is expected and is not evidence they did nothing.

`swapon --show` should list `/dev/zram0` (~3.8 G, zstd, prio 100). Confirmed
2026-09-01. To undo: delete the conf file and reboot.

## Storage — one command at a time

The obvious tuning advice for an NVMe SSD is "set the scheduler to `none`; the
device has 64 queues and 1023 tags, an elevator only adds CPU work". Ubuntu ships
`mq-deadline` here, and that looks like a bug worth fixing.

**It is not. Do not change it.** This controller is not a normal NVMe:

```
$ bin/io-probe
  model                 APPLE SSD AP0256H
  quirks                qdepth_one single_vector
  queue_count           2   (1 admin + 1 I/O)
  sqsize                1   (0-based, so 2 entries)
  usable tags           1   <- commands in flight
```

Apple's S1X controller (`106b:2001`) carries the kernel's **`qdepth_one`**
quirk. One I/O queue, one usable tag: **one command in flight, ever.** There is
no parallelism for `none` to preserve, and the only lever left is getting more
work into each command — which is exactly what the scheduler does:

```
  reads       54543  merged     17710  (25% of requests merged away)
  writes      55855  merged     60628  (52% of requests merged away)
```

A quarter of reads and half of writes never became a separate round-trip. On a
queue-depth-1 device each merge is a round-trip saved. `none` does only the
limited plug-list merging, so switching would give most of that back.

Baseline, cold cache via `POSIX_FADV_DONTNEED`:

```
  read_ahead_kb=128      seq   223.2 MB/s   rand4k   3821 IOPS (0.26 ms each)
```

0.26 ms per 4K random read is the whole story: every request waits for the last
one to finish.

`bin/io-probe` is read-only and needs no sudo. `--sweep` (root) walks
`read_ahead_kb` and restores the original value afterwards.

### The readahead sweep, measured (2026-09-04)

```
  read_ahead_kb=64       seq   214.2 MB/s   rand4k   6147 IOPS (0.16 ms each)
  read_ahead_kb=128      seq   218.3 MB/s   rand4k   5401 IOPS (0.19 ms each)
  read_ahead_kb=256      seq   210.9 MB/s   rand4k   5899 IOPS (0.17 ms each)
  read_ahead_kb=512      seq   220.9 MB/s   rand4k   3898 IOPS (0.26 ms each)
  read_ahead_kb=1024     seq   215.1 MB/s   rand4k   2427 IOPS (0.41 ms each)
```

**Leave it at 128.** The hypothesis was that 256 would win, because
`max_sectors_kb` is 256 and a bigger bite means fewer round-trips on a
one-command-at-a-time device. It does not. Sequential throughput is
210.9–220.9 MB/s across a 16x range of readahead — a 5% spread that is not even
monotonic (256 is the slowest, 512 the fastest), which is the shape of noise,
not of an effect.

Random 4K is the only real signal, and it goes the *other* way: 512 and 1024
cost 28% and 55% of the IOPS. That is the "cannot overlap" prediction coming
true — oversized readahead fetches data nothing asked for, and this controller
has to finish it before it can start the next request. 64/128/256 are within
noise of each other, so there is nothing to win, only something to lose.

`bin/doctor` records the queue depth, and warns if the scheduler is ever set to
`none`, so this does not get "fixed" later.

> Retracted here: an earlier pass through this machine flagged `mq-deadline` as
> wrong and recommended `none`, reasoning from what NVMe hardware normally is.
> The recommendation was not checked against this device before being made.
> `nr_hw_queues=1` and `nr_requests=2` were visible the whole time.

## Graphics / VA-API

libva auto-selects **`iHD`** (`intel-media-va-driver`), which targets Gen9+. This is
Gen8 Broadwell, and on this part iHD exposes decode only. **`i965`** is the Broadwell
driver and strictly dominates it here:

| | iHD (auto) | i965 |
|---|---|---|
| H.264 / MPEG2 / VP8 / JPEG decode | ✓ | ✓ |
| VC1, H.264 MultiviewHigh / StereoHigh | — | ✓ |
| **H.264 hardware encode** (`VAEntrypointEncSlice`) | **none** | ✓ |

Selected by [`config/X11/56mintbook-libva`](../config/X11/56mintbook-libva) →
`/etc/X11/Xsession.d/`, installed by [`bin/tune-install`](../bin/tune-install).
**Takes effect at the next login**, not immediately — `bin/doctor` warns until then.

[`config/environment.d/90-mintbook-libva.conf`](../config/environment.d/90-mintbook-libva.conf)
is still installed, and on its own it did nothing for a year of apps. See
[Why environment.d never reached anything](#why-environmentd-never-reached-anything-2026-09-04).

> **Neither driver can decode VP9 or AV1.** Broadwell has no such silicon. Sites that
> default to VP9/AV1 — YouTube among them — still decode on the CPU, and on a fanless
> chip that is felt. The driver swap does not fix that; only serving H.264 does.
> Whether Chrome picks up VA-API at all is a separate question: check `chrome://gpu`.

### What Chrome actually does (2026-09-04)

From a `chrome://gpu` export, Chrome 152, **taken while iHD was still the live
driver** — the session predated the `environment.d` file, so this is the *before*
picture, not the i965 one.

| | |
|---|---|
| Video Decode | **Hardware accelerated** |
| Decode profiles | h264 baseline / main / high, vp8 — 16x16 to 4096x4096 |
| Video Encode | **Software only. Hardware acceleration disabled** |
| Encode profiles | *(empty)* |
| Canvas / Compositing / Rasterization / WebGL | hardware accelerated |
| GL path | `gl=egl-angle, angle=opengl`, ozone x11 |
| GPU process crashes | 0 |

> **SUPERSEDED 2026-09-06 — read the note below this paragraph before acting on it.**

**Decode was already working.** The open question from the session that forced i965
— whether Chrome used VA-API at all — is answered: it does, and it did so before the
driver change. There is no decode win to collect here.

> **Corrected 2026-09-06 — this paragraph read the wrong thing.** The profile list
> above is Chrome reporting what the *driver* can do. Asked what the decoder stack
> actually chose while a video played, Chrome answers `FFmpegVideoDecoder` with
> `kIsPlatformVideoDecoder: false` — **software**, for YouTube H.264, YouTube AV1,
> and a plain `.mp4` alike, under **both** i965 and iHD, and under every flag tried.
> Chrome never uses VA-API on this machine. The conclusion "no decode win to
> collect" survives; the reason given for it does not. See [video.md](video.md).

**No VP9 and no AV1 in that list.** This is the empirical confirmation of the
Broadwell limit, not just the spec claim: YouTube's default codecs decode on the CPU,
and on a fanless chip that is the heat. The only lever is making sites serve H.264.

**Encode is off, and the export cannot say why.** Chrome reports it as "disabled,
either via blocklist, about:flags or the command line". Two candidate causes and this
dump does not separate them:

1. iHD exposes **no encode entrypoint at all** on this part — true at the time of the
   export, and sufficient on its own to explain an empty encode list.
2. Chrome's own gate on VA-API encode under Linux.

i965 does have `VAEntrypointEncSlice`, so **re-export `chrome://gpu` after the next
login** — that is the discriminator. If encode is still software-only with i965 live,
the cause is (2) and it needs a Chrome flag, not a driver. Worth chasing only if you
do video calls or screen recording; it does nothing for playback.

### Encode with i965 live — the discriminator, answered (2026-09-06)

**It is cause (2): Chrome's own gate, not the driver.** Re-exported `chrome://gpu`
from Chrome 152.0.7977.82 with `i965_drv_video.so` confirmed mapped in the GPU
process, and encode is *still* software-only.

| | i965 live, 2026-09-06 |
|---|---|
| VA driver mapped in GPU process | **`i965_drv_video.so`** |
| Video Decode | **Hardware accelerated** |
| Decode profiles | h264 baseline / main / high, vp8 — 16x16 to 4096x4096 |
| Video Encode | **Software only. Hardware acceleration disabled** |
| Encode profiles | *(still empty)* |
| GL path | `gl=egl-angle, angle=opengl`, ozone x11, Mesa 25.2.8 |

The decode list is byte-for-byte what iHD produced, so **the driver swap changed
nothing Chrome can see**. It was still worth doing for encode-capable *other*
consumers — `vainfo` under i965 reports `VAEntrypointEncSlice` for H.264, MPEG-2
and JPEG — but Chrome does not use it.

Four flag combinations were tried, each on a throwaway `--user-data-dir`, each
re-exporting `chrome://gpu`. **All four still reported software-only encode with
an empty profile list:**

| Flags | Result |
|---|---|
| *(none)* | software only |
| `--ignore-gpu-blocklist` | software only |
| `--enable-features=VaapiVideoEncoder` | software only |
| `--enable-features=AcceleratedVideoEncoder` | software only |

`--ignore-gpu-blocklist` ruling it out is the important one: **it is not the GPU
blocklist.** `Problems Detected` lists `video_encode` under `Disabled Features`
with no `crbug` reference, unlike every genuine blocklist entry on the same page,
which carries one.

Two further pieces of evidence that the encode path is never even reached:

- `--vmodule=*vaapi*=2,*video_encode*=2` produced **no VA-API log lines at all**.
  A gated-but-attempted initialisation would log; this does not start.
- The binary exports the feature name `AcceleratedVideoEncoder` and the switch
  `disable-accelerated-video-encode`, but **no corresponding enable switch**.
  There is no supported knob to turn on.

**Conclusion: stop chasing this.** Hardware H.264 encode in this Chrome build is
not reachable by configuration. It costs nothing for playback, which is decode.

> **Followed up the same day, and the advice that was here was wrong.** This
> section suggested reaching for `gst-launch-1.0` instead, on the grounds that
> i965 exposes `VAEntrypointEncSlice`. It does expose it, and **the encoder
> aborts**: `i965_encoder.c:1692: intel_enc_hw_context_init: Assertion
> `encoder_context->mfc_context' failed`, from both `vah264enc` and
> `vaapih264enc`, on the first frame. There is no working hardware H.264
> encoder on this machine under any driver. An advertised VA-API entrypoint is
> a claim, not a capability. See [video.md](video.md).

Raw export: [2026-09-06-chrome-gpu-i965.txt](measurements/2026-09-06-chrome-gpu-i965.txt).

Method, for repeating this without clicking through the UI: launch Chrome on a
throwaway profile with `--remote-debugging-port`, then read `chrome://gpu` over
the DevTools protocol. `document.body.innerText` returns **empty** — the page
builds its content inside the shadow root of an `<info-view>` element, so the
extraction has to walk `shadowRoot` recursively.

> **Restarting Chrome is not enough** — but the reason given here was wrong, and
> logging out would not have fixed it either. `/etc/environment.d` is not read by
> the session at all. See
> [Why environment.d never reached anything](#why-environmentd-never-reached-anything-2026-09-04).
>
> **Check which driver is mapped — not the environment.** The reliable test:
>
> ```bash
> grep -oE "(i965|iHD)_drv_video\.so" /proc/<gpu-process-pid>/maps | sort -u
> ```
>
> `/proc/<pid>/environ` produced a **false negative** here: it reported no
> `LIBVA_DRIVER_NAME` for a Chrome that demonstrably had `i965_drv_video.so`
> mapped. A test was called invalid on the strength of that and it was not.
>
> The mechanism, confirmed 2026-09-04: Chrome and Electron **overwrite** that
> memory region to set their process titles, so `/proc/<pid>/environ` reads back
> as blank entries — 1643 bytes of nothing for Chrome, nothing for Claude
> Desktop. Cursor happens not to scrub it, which is why it could be used as the
> probe below. The mapped library is what the process loaded; believe it over
> the environment.

To test it **without logging out**, launch one Chrome with the variable set by hand
and open `chrome://gpu` in that window:

```bash
LIBVA_DRIVER_NAME=i965 google-chrome-stable --user-data-dir=/tmp/cr-i965
```

There is no scripted version of this. `chrome://gpu` fills itself in from the GPU
process after load, so `--headless=new --dump-dom` returns the empty template — tried
under both drivers, 101116 bytes each, no `accelerated` anywhere in the output.

If it does turn out to need a Chrome flag (`--enable-features=VaapiVideoEncoder`),
note that **Google Chrome's `.deb` wrapper reads no flags file**. `/usr/bin/google-chrome-stable`
is a symlink to `/opt/google/chrome/google-chrome`, which sources nothing — the
`chrome-flags.conf` convention is a Chromium packaging thing, not this. The flag would
have to go on the `Exec=` line of the desktop entry.

### Why environment.d never reached anything (2026-09-04)

`bin/doctor` had been warning `iHD` since the file was written, and the standing
explanation was "log out to pick it up". That was wrong. Logging out would not
have helped, because **nothing in the desktop ever reads `/etc/environment.d`.**

`environment.d` is read by `systemd --user`, and applies to processes
`systemd --user` starts. The desktop is not one of them:

```
lightdm  ->  /etc/X11/Xsession  ->  55xfce4-session  ->  xfce4-session
```

Everything launched from the panel, the dock or Whisker inherits *that*
environment. Apps that end up in a systemd **scope** are not an exception —
Chrome sits in `app-com.google.Chrome-<pid>.scope`, but a scope adopts a process
that the session already forked, so it keeps the session's environment, not the
manager's.

The proof is a variable that ships in *both* places. `GTK_MODULES` is set by
`/etc/X11/Xsession.d/90atk-adaptor` **and** `/etc/environment.d/90atk-adaptor.conf`:

```
$ tr '\0' '\n' < /proc/$(pgrep -x cursor | head -1)/environ | grep -E 'GTK_MODULES|LIBVA'
GTK_MODULES=gail:atk-bridge
```

Same session, same two mechanisms, and only the `Xsession.d` one arrived.
`LIBVA_DRIVER_NAME`, which shipped only in `environment.d`, is absent. Chrome,
Cursor and Claude Desktop all had `iHD_drv_video` mapped; `systemctl --user
show-environment` had `LIBVA_DRIVER_NAME=i965` the whole time, which is exactly
the trap — the variable was set somewhere real, just not anywhere the
applications would look.

The driver was never the problem: `i965-va-driver` is installed, and
`LIBVA_DRIVER_NAME=i965 vainfo` reports `Intel i965 driver for Intel(R)
Broadwell - 2.4.1` with the encode entrypoints. It was only ever the plumbing.

Fixed by [`config/X11/56mintbook-libva`](../config/X11/56mintbook-libva) →
`/etc/X11/Xsession.d/56mintbook-libva`, which runs before
`95dbus_update-activation-env` — so the variable also lands in `dbus-daemon` and
`systemd --user` on the way through. It leaves an existing value alone, so
`~/.xsessionrc` (sourced earlier, at 40) still wins.

`environment.d` is kept: it is still the right place for `systemd --user`
services, which genuinely do read it. It was never the wrong file, only the
wrong file *on its own*.

**Not yet confirmed on a real login.** `doctor` now checks the driver a running
app has mapped, which is the test that cannot lie.

## Idle power and the display — measured, not assumed

[`bin/idle-probe`](../bin/idle-probe) reports package watts from RAPL, the real
FBC/PSR state, and every device's runtime-PM setting. `--try <BDF>` flips one
device to `auto`, samples watts, and restores the original — including on
Ctrl-C. RAPL, the `i915` parameters and `debugfs` are all `0400` on this kernel,
so the interesting half needs `sudo`.

**Nothing here was applied blind, and two candidates were withdrawn outright.**

### `snd_hda_intel power_save` — retracted, and now guarded

Flagged as an easy win: `power_save=0` when the Ubuntu default is 1. It is not
an oversight. `/etc/modprobe.d/mb81-singlecmd.conf` sets it deliberately, and
says why:

> The CS4208 class-D speaker amp rails (GPIO4/GPIO5) are set ONCE by EFI and the
> driver deliberately never re-drives them. A runtime-PM D3 cycle disturbs those
> rails and nothing restores them on the D0 resume: the clock recovers but the
> amp stays dead → SILENCE.

Setting `power_save=1` would trade a fraction of a watt for the speakers, until
the next reboot. `bin/doctor` now **fails** if it is ever not 0, because a
modprobe.d change or a kernel default flip would do this silently and the
symptom — no sound — looks nothing like its cause. See
[audio.md](audio.md).

### `i915.enable_fbc` — nothing to turn on

Flagged as "no i915 tuning is set". The parameters are not unset, they are
`-1`, which `modinfo` spells out as *"use per-chip default"* — the driver
already decides per platform. Confirmed as root, 2026-09-04:

```
  enable_fbc   -1   (per-chip default)
  enable_psr   -1   (per-chip default)
  enable_dc    -1   (per-chip default)
  enable_ips    Y   (already on)
``` Forcing `enable_fbc=1` does not enable something
that was off; it overrides a per-chip decision, on a Gen8 part, in a driver that
has had FBC reworked repeatedly. `idle-probe` reports the actual state when run
as root. Change it only if that shows FBC off **and** a `--try` measurement
shows it is worth something.

### PCI runtime PM — the safe set is smaller than it looks

Eleven devices sit at `power/control=on` and never enter D3. `auto` is what
`powertop` calls a Good tunable, and on a fanless chassis idle watts are thermal
budget — so it is worth measuring. It is not worth applying blind here, because
of what those devices are:

| Device | Why not blind |
|---|---|
| `00:15.4` | applespi — the keyboard and trackpad. Already `auto`, and it works. Leave it |
| `00:15.5` | the Bluetooth UART. See [bluetooth.md](bluetooth.md) for what it took to get an adapter at all |
| `01:00.0` | Wi-Fi. `brcmfmac` runtime PM is a well-known source of dropped links |
| `02:00.0` | the FaceTime camera — out-of-tree DKMS that needs `intel_iommu=off` to DMA at all |
| `03:00.0` | the NVMe controller, which already power-manages itself through APST (`default_ps_max_latency_us=100000`) |

`idle-probe --try` refuses those five without `--force`. The unremarkable ones —
`00:16.0` (MEI), `00:1f.6` (thermal), `00:14.0` (xHCI) — are where to start.

### A measurement that lied (2026-09-04)

The first `--try 0000:00:16.0` looked spectacular:

```
  baseline (control=on), 5s ...     package-0  3.43 W   core 1.54 W   dram 1.08 W
  control=auto, 5s ...              package-0  2.06 W (-1.38 W)
                                    core 0.69 W (-0.86 W)   dram 0.61 W (-0.47 W)
```

A 40% drop in package power from letting a management-engine **mailbox** nap.
It is not real, and the giveaway is in the same output: 0.86 W of it came out
of **core**, and 0.47 W out of **dram**. Whatever MEI does, it cannot make the
CPU cores or the memory controller use less power. The two five-second windows
simply had different background activity, and the tool attributed all of it to
the one thing that changed on purpose.

`--try` now alternates: `--cycles` pairs of samples, `on`/`auto`/`on`/`auto`,
reporting the mean of each arm, the widest within-arm spread as a **noise
floor**, and a verdict that says *not measurable* whenever the difference is
smaller than that floor. Drift lands in both arms instead of only the second.

> This is the second time on this machine that a straight before/after has
> flattered a change — the genmon rewrite measured 11.6% → 7.8% only because
> the second window was busier, and the plugins that were *not* touched proved
> it by rising too. On a machine with a live desktop and browsers, a single
> pair of samples is not a measurement. Interleave, and print the noise.

`idle-probe` uses **BAT0 while discharging** in preference to RAPL, because
RAPL only sees the SoC package and every device worth testing here is on its own
rail. Measured side by side on an idle battery machine:

```
  BAT0        6.88 W     whole system
  package-0   3.82 W     SoC only  (core 1.61, uncore 0.12, dram 1.16)
```

**RAPL sees 55% of the draw.** The missing 3.06 W is the backlight, Wi-Fi, the
SSD and the rest of the board — which is exactly where a runtime-PM saving would
show up, and exactly what RAPL cannot see. `current_now` is world-readable, so on battery the measurement needs no
root — only flipping the device does. On AC, `current_now` is *charge* current
and says nothing about draw, so the tool falls back to RAPL there.

### The battery sensor is noisier than the thing being measured

Twelve one-second samples of an idle-ish 12 W draw:

```
  mean 12.05 W   min 10.69   max 13.37   spread 2.67 W
```

A **2.67 W** spread, to look for a device that might be worth 0.3 W. A
before/after pair here is worthless — it would report whatever the sensor
happened to be doing.

What makes it tractable is that the uncertainty of a *mean* shrinks as
`1/sqrt(n)`. So `--try` collects one reading per second across many alternating
arms and reports **mean ± standard error**, the difference, and the size of
effect the run could actually resolve:

```
  on   mean  11.90 W  +/- 0.075  (n=120)
  auto mean  11.72 W  +/- 0.071  (n=120)
  difference  -0.18 W
  this run could resolve about 0.21 W
  VERDICT: NOT MEASURABLE. Any real effect is smaller than 0.21 W ...
```

The defaults on battery are 6 cycles x 20 s per arm — about four minutes, 120
samples per arm, enough to resolve roughly 0.2 W. More `--cycles` narrows it,
slowly, by the square root.

### Result: MEI runtime PM, measured (2026-09-04)

```
  on   mean   6.13 W  +/- 0.030  (n=120)
  auto mean   6.09 W  +/- 0.021  (n=120)
  difference  -0.04 W
  this run could resolve about 0.07 W
  runtime_status while on auto: suspended
  VERDICT: NOT MEASURABLE.
```

**Under 0.07 W. Not worth having.** The device genuinely did suspend — the
`runtime_status` line is there to prove the test actually happened rather than
silently doing nothing — and it still saved nothing findable.

The run is also the clearest evidence yet for why the arms are interleaved. The
running means fell monotonically in *both* arms, because the machine was still
settling down from earlier benchmarking:

```
    cycle 1   on 6.47   auto 6.22   gap -0.25
    cycle 3   on 6.33   auto 6.21   gap -0.12
    cycle 6   on 6.13   auto 6.09   gap -0.04
```

Drift across the run was about **0.54 W**. The effect under test was **0.04 W** —
so the drift was **14x the signal**. A naive "measure A for 20 s, then B for
20 s" would have reported roughly 0.20 W of savings, five times the truth and
all of it the machine calming down. Watch the gap converge from -0.25 to -0.04
as the drift averages equally out of both arms: that is the method working,
live.

The remaining `control=on` devices are small on-chip controllers of the same
order. This avenue is closed unless something suggests otherwise.

> thermald logs `NO RAPL sysfs present` on this machine. It is wrong:
> `/sys/class/powercap/intel-rapl:0/` is there with package, core, uncore and
> dram domains. thermald is looking for the MSR interface, not powercap. One
> more reason it was not doing the job it was kept around for.

## CPU mitigations — your call, with a number

Measured on this machine, pinned, `mitigations` at their defaults:

```
raw getpid syscall   ~720 ns     (about 1450 cycles at 2 GHz)
```

An unmitigated `getpid` on this class of core is 150–300 cycles. Nine
mitigations are active, and the syscall path carries most of them: PTI (a page
table switch per entry and exit), MDS buffer clearing (a `VERW` on every return
to userspace), and retpolines on the indirect branches in between.

That tax lands hardest on exactly what this machine runs — Node, git, Electron
IPC — all syscall- and context-switch-bound.

`mitigations=off` would give most of it back. It also turns off Meltdown and MDS
protection on a CPU that is genuinely vulnerable to both. **This is a security
posture decision, not a performance bug, so it is written down here and not
applied.** The trade is only reasonable if you accept that a malicious page in a
browser tab is the threat model you are opting out of, on a machine that browses.

It is a boot argument. **Corrected:** an earlier version of this section said
that because OpenCore is the picker, editing `/etc/default/grub` does nothing.
That is wrong, and [boot.md](boot.md) already had the answer. OpenLinuxBoot is
in autodetect mode and reads `GRUB_CMDLINE_LINUX_DEFAULT` straight out of
`/etc/default/grub` — no `update-grub`, no `config.plist` edit. It is how
`intel_iommu=off` got onto the cmdline for the camera, confirmed 2026-09-01.

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 mitigations=off"/' /etc/default/grub
grep GRUB_CMDLINE_LINUX_DEFAULT /etc/default/grub    # check before rebooting
```

Reverting is deleting the word again. If a boot ever does go wrong, OpenCanopy
still offers 6.14 and macOS — see [boot.md](boot.md) Rollback safety.

Re-measure after the reboot:

```bash
gcc -O2 -o /tmp/sc - <<'EOF' && taskset -c 3 /tmp/sc
#define _GNU_SOURCE
#include <stdio.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>
int main(void){ struct timespec a,b; const long N=2000000;
  syscall(SYS_getpid); clock_gettime(CLOCK_MONOTONIC,&a);
  for(long i=0;i<N;i++) syscall(SYS_getpid);
  clock_gettime(CLOCK_MONOTONIC,&b);
  printf("%.1f ns\n",((b.tv_sec-a.tv_sec)*1e9+(b.tv_nsec-a.tv_nsec))/N); }
EOF
```

`bin/doctor` reports the state either way and never treats it as a fault.

### Measured, after (2026-09-04)

Applied via `GRUB_CMDLINE_LINUX_DEFAULT="intel_iommu=off mitigations=off"`, one
reboot. `/sys/devices/system/cpu/vulnerabilities/` goes from 9 mitigated to 1.

```
                     before    after
raw getpid syscall   ~720 ns   127 ns      5.7x
```

Both measurements pinned to cpu3, same binary, comparable load (0.5-1.0 min
load 2.74 before, 2.98 after). This is the trustworthy number: it is the thing
the change acts on, measured directly.

Knock-on effects, **consistent with that but not controlled** — the "before"
figures were taken under a heavier load and cannot be re-run without rebooting
back:

```
python3 -c pass       50 ms -> 31 ms
panel-cpu             65 ms -> 45 ms
panel-power           29 ms -> 21 ms
panel-bt              23 ms -> 19 ms
```

Interpreter startup is thousands of `stat`/`open`/`mmap` calls, so it should
move the most, and it does. Disk throughput is unchanged at ~222 MB/s, which is
the sanity check — it is not syscall-bound, so it should not have moved, and it
did not.

Everything else survived the reboot: camera, audio, Bluetooth, trackpad, i965,
and the boot-time CPU cap. `bin/doctor` reads 51 ok, 1 warn, 0 FAIL, the warning
being this choice.

**Undo** is one word and a reboot:

```bash
sudo sed -i 's/ mitigations=off//' /etc/default/grub
```

## Housekeeping

- **Journal was uncapped.** Stock `journald.conf` is empty, so the default is 10% of
  the filesystem; it had reached 302 MB. Capped to 100 MB by
  [`config/systemd/journald-mintbook.conf`](../config/systemd/journald-mintbook.conf)
  → `/etc/systemd/journald.conf.d/mintbook.conf`. Now 96 MB.
- **`casper-md5check.service` was enabled and failing on every boot.** It verifies a
  live ISO's checksums; there is no ISO when booting from disk. Masked.
  `systemctl --failed` is now empty, which is the point — it is only a useful signal
  if it is normally clean.
- **`thermald` was running blind and undoing the power policy.** Masked by
  `bin/tune-install`. It found no RAPL, no coretemp and no thermal zones on this
  machine, so it manages nothing — but it still writes `max_perf_pct`, and it
  starts after `mintbook-power.service`, which is how the battery cap went
  missing on every boot. Full trace in
  [The cap did not stay put](#the-cap-did-not-stay-put-2026-09-04). The thermal
  backstop is unaffected: that is the CPU's TCC throttle, in silicon.
- **`evolution-data-server` started four processes at every login** (alarm-notify,
  source-registry, calendar-factory, addressbook-factory) with no Evolution installed.
  Disabled with a `Hidden=true` override in `~/.config/autostart/`, the same pattern
  already used for `nm-applet` — see [desktop.md](desktop.md).
### Services this machine has no use for (2026-09-04)

[`bin/service-trim`](../bin/service-trim) masks them. **Every entry is behind a
probe** — nothing is masked because a list said so. Run it with `--check` first;
that needs no root and changes nothing.

| Masked | Probe |
|---|---|
| `ModemManager` | no `/dev/cdc-wdm*`, no `/dev/ttyACM*`, no modem-class PCI device. It probes serial ports on every device event |
| `cups`, `cups.socket`, `cups.path`, `cups-browsed` | `lpstat -p` has no destinations and `printers.conf` is empty. The socket and path units re-activate CUPS on demand, so masking the service alone does nothing |
| `switcheroo-control` | one GPU. `lspci` counts a single `[0300]` |
| `casper`, `casper-md5check` | `/` is not an `overlay` mount, so this is not a live boot |
| `rsyslog` | `/var/log/journal` exists, so journald already stores this. Syslog was a second copy of the same lines |
| `kerneloops` | opt-in crash-signature upload |

Deliberately **left running**, and the reason matters more than the list:

- **`iio-sensor-proxy`** — this machine has a real ambient light sensor.
  `monitor-sensor` reports `Has ambient light sensor` and live lux values. It is
  doing work; a debloat list would have killed it.
- **`avahi-daemon`** — `nsswitch.conf` has `mdns4_minimal`. Masking it breaks
  `.local` name resolution and Warpinator discovery.
- **`light-locker`** — the screen locker.
- **`mintUpdate`** — this machine needs kernel 7.0 specifically. Losing update
  notifications on it is not a trade worth making for 88 MB.

Undo is per-unit: `systemctl unmask --now <unit>`. `bin/doctor` reports which of
the set are still enabled rather than asserting they are gone, because an update
can re-enable one and a printer appearing is a legitimate reason for CUPS to
come back.

> A `systemctl is-enabled X | grep -q masked` test is wrong under
> `set -o pipefail`. `is-enabled` exits non-zero for a masked unit *while
> printing* `masked`, and pipefail propagates that over grep's success. It cost
> a real bug here: `power-check` reported a masked thermald as "not running",
> and `service-trim` offered to mask units that were already masked. Capture it
> instead: `[ "$(systemctl is-enabled X 2>/dev/null || true)" = masked ]`.

- `fstrim.timer` was already enabled. `nm-applet`'s user autostart entry is a
  deliberate `Hidden=true` override, not a stray duplicate — leave it.

## bin/doctor

The pieces that keep this hardware alive are scattered across `/etc/udev`,
`/etc/systemd`, `/etc/modprobe.d`, `/etc/libinput`, `/usr/local/sbin`,
`/lib/firmware`, two DKMS modules and a DSDT override inside the initrd. A kernel or
Mint update is exactly what quietly removes one of them, and the symptom shows up as
"the speakers stopped working" weeks later.

```bash
bin/doctor
```

Read-only, no sudo, exits non-zero on any FAIL. It checks the running kernel, the
power policy and its units, live thermals, zram and its sysctls, the VA-API driver,
the CS4208 codec and its DKMS module, the camera firmware + DKMS + `intel_iommu=off`,
the Bluetooth DSDT override and `hci0`, the SPI input quirks, panel size vs
`xfwm4 margin_top`, the genmon plugins, failed units, the journal cap and battery
health. **Run it after every kernel update.**

`doctor --tsv` prints the same run as `status<TAB>label<TAB>detail` lines, with a
`section<TAB>name<TAB>` line before each group. That is what
[`bin/mintbook-health`](../bin/mintbook-health) — the Doctor detail window behind
the System tray counts — reads; see docs/daily.md.

> Do not put `set -o pipefail` in it. `grep -q` exits on first match, the writer gets
> SIGPIPE, and the pipeline reports 141 — which reads as a hardware failure. That is
> what the first version of the CS4208 check did.

## Base toolchain

Present on a stock install: `git`, `python3` (3.12), `gcc`, `make`, `curl`, `dkms`,
`timeshift`, kernel headers for **7.0.0-30-generic**. Added for this machine:
`libinput-tools`, `systemd-zram-generator`.

**Absent:** `node`, `npm`, `jq`, `gh`, `docker`, `rustc`, `go`, `java`. Claude Desktop
is installed as a `.deb` and bundles its own runtime under
`/usr/lib/claude-desktop`, which is why it runs with no system Node present.

Screenshot tooling is **`xfce4-screenshooter` only** — no `scrot`, `maim` or `import`.
This keyboard has no Print key; the bindings are **Cmd+Shift+3 / 4 / 5**
(saved under `~/Pictures/Screenshots/`, see [desktop.md](desktop.md)).

### 2026-10-08: power-request isolation

The desktop-writable `/run/mintbook-power` directory is only the request inbox.
The authoritative cap moves to `/run/mintbook-policy/cap`, under a root-owned
0755 directory, and is replaced atomically without following a leaf symlink.
Input Boost reads that new path. Requests must be short regular files; symlinks
and FIFOs are refused without blocking. Reinstall with `sudo bin/power-install`
after a Timeshift snapshot, then restart Input Boost. No tuning values change.
