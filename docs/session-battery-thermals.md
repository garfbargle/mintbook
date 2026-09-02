# Session prompt — battery and thermals

**Done 2026-09-01.** Policy is installed. Record: [hardware.md](hardware.md) Thermals.
Do not re-run this session unless undoing the hook or measuring discharge off the
charger. Unplug once and run `bin/power-check` — it should show `power-saver` and
`max_perf_pct=70`.

Paste the block below into a **new** chat in this repo (`/home/cobo/mintbook`).
The rest of this file is that prompt, so the session can also be told:
“follow `docs/session-battery-thermals.md`.”

---

You are working in **mintbook**: Linux Mint 22.3 XFCE/X11 on a **2015 12-inch MacBook (MacBook8,1)**, fanless Core M-5Y31, 7.7 GB RAM, 2304×1440. This repo is the record. Read first, then measure, then change. Do not re-solve working hardware.

**Read, in order:**
- `README.md` (conventions: diagnostics before claims; record what was ruled out; sudo only for package/module work and write the steps; GRUB is not the boot loader)
- `docs/hardware.md` (thermals, battery, swap/zram — zram is **done**, do not redo it)
- `docs/desktop.md` — Open/not done: thermals; also “no picom / no blur” (performance)
- `docs/boot.md` only if you think you need a kernel argument. You almost certainly do not. OpenCore is the loader; `update-grub` is a no-op. `config.plist` is already recorded; do not edit it.
- `bin/hw-report` and `sensors` for live numbers. Panel temp is `bin/panel-temp` (coretemp by name).

**This session’s job:** make the machine **run cooler and last longer on battery** during normal desktop use (Chrome + Cursor/Electron). Not a driver hunt. Speakers, camera, Bluetooth, SPI input, HiDPI, and the panel are working — leave them.

**Hardware facts (do not rediscover):**
- Fanless. It throttles at **95 °C** (`high`/`crit` both 95). Idle has been ~60 °C; sustained desktop work 73–88 °C; this chassis has been seen at **83–94 °C package** with Cursor+Chrome.
- Battery ~84–85% health, ~149 cycles. Discharge has been measured around **10–14 W** (~2.5 h at ~77% charge). Charging rate is high (~16 W observed) — that also heats the chassis.
- `power-profiles-daemon` is installed. Profile is **`balanced`**. **`power-saver` is unused.** Driver: `intel_pstate`. Governor: `schedutil`.
- `thermald` is **active and enabled**. `tlp` / `auto-cpufreq` are **not** installed. Do not stack TLP on top of power-profiles-daemon without a reason and a timeshift.
- xfce4-power-manager: lid-on-battery = suspend (`1`); **lid-on-AC is unset**; power button = 3. `/sys/power/mem_sleep` is `s2idle [deep]` — one successful **deep** suspend exists in the journal (2026-08-31). Sleep is adjacent to battery life but is **not** the primary goal unless you need it for idle drain. Hibernate is impossible (zram is not a hibernation image).
- User declined real blur (picom) on performance grounds. There is no picom. Do not add a compositor pass to “save power.”
- Display backlight is `acpi_video0`. Keyboard backlight works and is already documented; only touch it if it is wasting power at idle (it was at 0 when last checked).

**Approach:**
1. Baseline *before* changing anything: `sensors`, `upower` energy-rate on battery, `powerprofilesctl get`, package/core temps at idle vs with Cursor+Chrome. Write the numbers into `docs/hardware.md`. Idle means a quiet desktop, not mid-compile.
2. Prefer **small, reversible** policy: `power-saver` on battery, keep `balanced` on AC, or an xfce4-power-manager / `powerprofilesctl` hook. Measure whether package temp and watts actually drop.
3. Check RAPL / intel_pstate energy-performance preference, i915 powersave (`enable_psr` etc.) only with evidence. `intel_iommu=off` stays — camera needs it.
4. If you touch kernel cmdline, OpenLinuxBoot reads `/etc/default/grub` (no `update-grub`). Snapshot first: `sudo timeshift --create --comments "before thermals"`. There is no TTY sudo in this agent; use `pkexec` for a GUI prompt.
5. Record every miss in the doc (ruled out). Update the hardware status matrix and `docs/desktop.md` Open/not done when done.
6. Commit and push only if the user asks.

**Done looks like:** idle and light-desktop temps and watts are written down (before/after); on-battery profile is intentional; nothing else on the machine was “fixed” as collateral.
