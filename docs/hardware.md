# Hardware status

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

> `/sys/class/power_supply/BAT0/capacity` is the **charge** percentage;
> `upower`'s `capacity:` field is **health**. They are different numbers and are easy
> to confuse.

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
| RAPL PL1 | firmware default **~46–49 W** on a **4.5 W TDP** chip. Writes do not stick |
| `thermald` | active, polling, stock (no `thermal-conf.xml`). Leave it — 95 °C backstop |
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
  `/run/mintbook-power/want`, root applies it. **No password on click.**
- [`config/systemd/mintbook-power-settle.timer`](../config/systemd/mintbook-power-settle.timer)
  + [`.service`](../config/systemd/mintbook-power-settle.service) — re-applies the
  cap 90 s after boot, once thermald and PPD have started. See below.
- [`config/tmpfiles.d/mintbook-power.conf`](../config/tmpfiles.d/mintbook-power.conf)
  → `/etc/tmpfiles.d/` (`/run/mintbook-power` owned `root:cobo`, mode 0770)
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
carries `After=power-profiles-daemon.service`, which does nothing here: PPD is
D-Bus-activated, so it starts when something first asks for it — 45 s *after*
the unit that was supposed to be ordered behind it.

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

**Decode was already working.** The open question from the session that forced i965
— whether Chrome used VA-API at all — is answered: it does, and it did so before the
driver change. There is no decode win to collect here.

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
