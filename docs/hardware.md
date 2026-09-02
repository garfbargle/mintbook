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
- [`config/tmpfiles.d/mintbook-power.conf`](../config/tmpfiles.d/mintbook-power.conf)
  → `/etc/tmpfiles.d/` (`/run/mintbook-power` owned `root:cobo`, mode 0770)
- [`config/polkit/org.mintbook.power.policy`](../config/polkit/org.mintbook.power.policy)
  + [`10-mintbook-power.rules`](../config/polkit/10-mintbook-power.rules) — leftover
  `pkexec` from a terminal, not used by the panel

The **panel icon** (genmon, left of the battery) is the switcher. XFCE Power
Manager settings has no power-profiles UI in 4.18. Click the gauge icon for
Power Saver / Balanced / Performance. Plug or unplug still reapplies auto. CLI
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
sudo systemctl disable --now mintbook-power.service mintbook-power-request.path
sudo rm -f /usr/local/sbin/mintbook-power-apply \
           /etc/udev/rules.d/99-mintbook-power.rules \
           /etc/systemd/system/mintbook-power.service \
           /etc/systemd/system/mintbook-power-request.path \
           /etc/systemd/system/mintbook-power-request.service \
           /etc/tmpfiles.d/mintbook-power.conf \
           /usr/share/polkit-1/actions/org.mintbook.power.policy \
           /etc/polkit-1/rules.d/10-mintbook-power.rules
echo 100 | sudo tee /sys/devices/system/cpu/intel_pstate/max_perf_pct
powerprofilesctl set balanced
```

### Ruled out

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

`swapon --show` should list `/dev/zram0` (~3.8 G, zstd, prio 100). Confirmed
2026-09-01. To undo: delete the conf file and reboot.

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
