# Input — Apple SPI keyboard and trackpad

**Status: working at boot; deep sleep proven broken; s2idle ready for verification.** Three separate
problems:

| | |
|---|---|
| Dead at boot | **Fixed.** `dw_dmac_pci` is blacklisted, so SPI always uses PIO. |
| Dead after sleep | **Deep S3 proven broken.** A controlled 2026-09-08 cycle captured 47 timeouts and a failed reprobe. `bin/input-install` now selects s2idle at boot; its first controlled cycle is next. |
| Palm / typing | **Quirk installed.** Disable-while-typing was a no-op until the keyboard was marked internal. **Log out once** for Xorg to reload it. |

`bin/input-check` reports all three. `sudo bin/input-install` copies the quirk and
blacklist (if missing), and selects the working sleep mode.

**Two different failures look identical from the chair: no keyboard, no trackpad.**
They are told apart by `using PIO` and by whether the machine slept —
`bin/input-check --history` now prints a `SLEPT` column for exactly this reason.

---

## 1. The boot race (keyboard and trackpad dead)

**This is the single most important thing to know about this machine.**

The built-in keyboard and trackpad fail **intermittently at boot**, roughly half the
time, unless the DMA blacklist is in place. It is **not** tied to a kernel version,
and it is **not** a broken install. It is a probe-order race.

### Symptom

Boot, and sometimes the keyboard and trackpad are simply dead. The machine looks
hung. Rebooting a few times eventually lands on a good boot. There is no pattern the
user can see, which is what makes it so unpleasant to diagnose.

### The mechanism

The keyboard and trackpad are **SPI-attached** (`applespi` on `spi-APP000D:00`, behind
the `pxa2xx_spi_pci` controller at PCI `00:15.4`) — not USB, not I2C.

DMA on that SPI controller **does not work on this hardware**. PIO does. Which one gets
used is decided by a race at boot:

**Good boot** — SPI probes before the DMA engine registers, so it falls back to PIO:

```
pxa2xx_spi_pci 0000:00:15.4: no DMA channels available, using PIO
dw_dmac_pci 0000:00:15.0: DesignWare DMA Controller, 8 channels
input: Apple SPI Keyboard ...
input: Apple SPI Touchpad ...
applespi spi-APP000D:00: modeswitch done.
```

**Bad boot** — the DMA engine registers first, SPI takes DMA, and every transfer dies:

```
dw_dmac_pci 0000:00:15.0: DesignWare DMA Controller, 8 channels
input: Apple SPI Keyboard ...
applespi spi-APP000D:00: SPI transfer timed out
applespi spi-APP000D:00: Error writing to device: -110      (ETIMEDOUT)
spi_master spi1: failed to transfer one message from queue
```

Note that on a bad boot the **keyboard input device still registers** — it is just
dead. The tell is that the **touchpad never appears** and `modeswitch done.` is never
reached.

### The evidence

Recorded before the blacklist was installed, both kernels:

| boot | kernel | `using PIO` | SPI timeouts | touchpad | result |
|---|---|---|---|---|---|
| -9 | 6.14 | yes | 0 | yes | works |
| -8 | 6.14 | yes | 0 | yes | works |
| -7 | 7.0 | yes | 0 | yes | works |
| -6 | 7.0 | yes | 0 | yes | works |
| -4 | 6.14 | **no** | 98 | no | **dead** |
| -3 | 6.14 | yes | 0 | yes | works |
| -2 | 7.0 | **no** | 163 | no | **dead** |
| 0 | 7.0 | yes | 0 | yes | works |

**Correlation with `using PIO` is 100%, across both kernels.** 6.14 works when it wins
the race (boot -3) and 7.0 fails when it loses (boot -2). Any claim that "6.14 has no
keyboard" is a sampling artefact — do not act on it.

Reproduce the table with:

```bash
bin/input-check --history
```

### The fix

Remove the race by removing the DMA provider, so SPI always falls back to PIO.
**Nothing else on this machine uses that DMA engine** — all 8 channels read
`in_use=0` even on a good boot.

Installed at `/etc/modprobe.d/blacklist-dw-dmac.conf` (also applied by
`bin/input-install` if the file is missing):

```
blacklist dw_dmac_pci
install dw_dmac_pci /bin/false
```

**No initramfs rebuild is needed** — `dw_dmac_pci` is not in the initramfs (only the
`dw_dmac` platform variant is), so it loads after the root pivot where
`/etc/modprobe.d/` already applies.

**No GRUB change, and no kernel command line change** — see [boot.md](boot.md) for why
neither would take effect on this machine anyway.

To undo, delete the file and reboot.

After rebooting, `bin/input-check` should report `using PIO`, zero timeouts, both
devices present, and `dw_dmac_pci not loaded`.

### Consequences

- **6.14 was not broken for input.** The race hits every kernel. 6.14 is kept as
  a boot fallback; speakers only work on 7.0 — see [audio.md](audio.md) and
  [boot.md](boot.md).
- This is very likely the cause of the long, miserable session of black screens and
  unresponsive boots that preceded this investigation. Combined with a boot menu that
  is easy to mis-navigate ([boot.md](boot.md)), a dead-input boot is hard to tell apart
  from a failed boot.

---

## 2. Dead keyboard and trackpad after deep sleep

**Every suspend this machine has ever taken has killed input. Two for two.**

This is *not* the boot race coming back, and that matters: the reflex is to blame
DMA again, and the blacklist is not the problem.

### Symptom

Close the lid or suspend. On wake the screen comes back, the machine is otherwise
alive, and the keyboard and trackpad are dead. They never recover — applespi retries
about once a second, forever, until a hard reboot.

### The mechanism

The SPI controller resumes perfectly. Checked on a live resume:

- `pxa2xx_spi_pci 00:15.4` comes back at `power_state: D0`, `runtime_status: active`
- the controller does **not** re-probe across suspend, so it stays on PIO
- `dw_dmac_pci` is still absent — the blacklist held

What fails is the **device re-init**, not the bus. On resume applespi cannot complete
a single transfer:

```
ACPI: PM: Waking up from system sleep state S3
applespi spi-APP000D:00: SPI transfer timed out
applespi spi-APP000D:00: Error writing to device: -110      (ETIMEDOUT)
spi_master spi1: failed to transfer one message from queue
```

**`modeswitch done.` is never reached after a wake.** That is the same tell as a bad
boot — and the reason the two failures are so easy to confuse.

`/sys/power/mem_sleep` is `s2idle [deep]`, so this is S3. Deep sleep is what breaks it.

### The evidence

Every boot in the journal, with and without a suspend:

| boot | slept | SPI timeouts | `modeswitch` after wake | result |
|---|---|---|---|---|
| -6, -5, -4, -3 | no | 0 | — | works |
| **-2** | **yes** | **106** | **no** | **dead on resume** |
| **-1** | **yes** | **77** | **no** | **dead on resume** |
| 0 | no | 0 | — | works |

**Correlation with suspend is 100%.** Both slept boots probed cleanly first — PIO,
touchpad present, zero timeouts — and only started failing after the wake. Boot -1
logged its first timeout in the same second as `Waking up from system sleep state S3`
and its last one 16 seconds later, when the machine was power-cycled.

Reproduce with:

```bash
bin/input-check --history
```

### The failed recovery experiment

The first workaround rebound `spi-APP000D:00` after wake, expecting a fresh probe
to repeat the working boot path. The controlled 2026-09-08 cycle disproved it:

```
deep sleep       8m25s
kernel wake      2.83s
SPI timeouts     47 in the report window
rebind           failed after 3 attempts
built-in input   missing; power-button reboot required
```

The full journal continued logging one timeout per transfer until reboot. A rebind
only repeats `applespi` probe against the same bad firmware link. Linux's driver
checks `SIST`, sees that firmware still calls SPI enabled, and skips `SIEN(1)` and
its recovery delay. The [driver's upstream repository](https://github.com/cb22/macbook12-spi-driver)
still lists "Resume on MacBook8,1" under what does not work.

The automatic rebind hook and script are removed by the current installer. They
were useful as a hypothesis and are now measured evidence against that hypothesis.

### The fix: avoid the broken S3 path

This machine exposes `s2idle [deep]`. Deep enters ACPI S3 and breaks the Apple SPI
endpoint. Suspend-to-idle freezes userspace and preserves the session without
taking that firmware path. It costs more battery during long sleeps, but it keeps
ordinary lid suspend usable and avoids a forced reboot after every wake.

[`mintbook-s2idle.service`](../config/systemd/mintbook-s2idle.service) selects it at
boot. Install it and retire the failed rebind hook with:

```bash
sudo bin/input-install
```

`bin/daily-install` also sets both Xfce lid actions to Suspend. This matters on
external power: Xfce does not reconsider a lid that was already closed when the
charger is later unplugged.

The selected mode is visible between brackets:

```bash
cat /sys/power/mem_sleep       # want: [s2idle] deep
bin/input-check                # want: sleep mode: s2idle
```

To undo the boot default, disable and remove `mintbook-s2idle.service`, then reboot
or write `deep` to `/sys/power/mem_sleep`.

### Verification status

Deep S3 and the old recovery are conclusively failed. The next controlled cycle
must verify s2idle: arm `sleep-report`, close the lid, and confirm zero Apple SPI
timeouts plus working keyboard and trackpad. Several longer cycles are needed to
measure the battery tradeoff.

### The sleep black box

[`bin/sleep-report`](../bin/sleep-report) turns the next normal lid close into a
measured cycle. It does **not** suspend the machine itself:

```bash
sleep-report arm       # then close the lid or suspend normally
sleep-report status    # armed state, or the latest result
sleep-report history   # the last 20 cycles
sleep-report json      # complete latest record, including relevant journal rows
sleep-report cancel    # disarm without sleeping
```

Cmd+Space also offers **Arm a sleep check** and **Show last sleep result**. The
watcher is a transient user service. It exists only after `arm`, exits after one
resume, and expires after 36 hours. No permanent timer, system hook, root change
or extra sampling daemon is installed.

Linux freezes the watcher with the rest of userspace during suspend.
`CLOCK_BOOTTIME` includes suspended time and `CLOCK_MONOTONIC` does not, so the
increase in their difference is the measured sleep duration. While armed, the
watcher refreshes the battery counter once a second; this puts the pre-sleep
reading within roughly one second of suspend without writing every reading to
disk. After wake it waits 12 seconds for input and desktop services to settle,
then records:

- elapsed sleep time and estimated Wh / percentage-point loss;
- average sleep watts when both ends were discharging;
- kernel wake timing from the wake and `PM: suspend exit` journal markers;
- selected sleep mode, built-in keyboard and trackpad presence, and SPI timeouts;
- Wi-Fi reconnection, Bluetooth adapter state and the default PipeWire sink;
- priority-3 journal errors and relevant suspend/applespi messages in the cycle.

Battery Wh uses `energy_now` when available. This MacBook exposes charge, so the
fallback is `charge_now × voltage_min_design`; using the fixed design voltage
prevents ordinary voltage sag from looking like energy loss. A charger state
change or rising gauge is reported as unmeasurable rather than negative drain.
One cycle is evidence about recovery, but overnight drain needs several cycles.

Records live under `~/.local/state/mintbook/sleep-report/`: `latest.json` and an
append-only `history.jsonl`. `armed.json` exists only while armed (or after an
expiry). `daily-install --revert` removes the command but deliberately retains
the measurements.

Validation covers clean, failed, deep and s2idle resume fixtures,
charger transitions, a rising battery gauge, journal filtering, kernel timing and
report formatting. The complete 35-test suite passes. The first live capture found
the deep-sleep failure above and persisted it across the required reboot. A second
capture remains armed for the first s2idle cycle. The 2026-09-08/09 overnight lid
close did not exercise it: the laptop was on external power, Xfce's AC lid action
was absent, and the journal contains no suspend entry. The machine stayed awake and
warm until morning. Both lid actions are now installed as Suspend, with their prior
values included in `daily-install --revert`.

### Ruled out

- **The DMA race.** The controller stays on PIO across suspend and `dw_dmac_pci`
  never loads. Verified on the live resume above.
- **A dead controller.** It resumes to D0 and accepts messages; they time out at the
  device, not the bus.

---

## 3. Palm rejection / disable-while-typing

The pad works. Resting a palm on it while typing still moved the cursor and tapped
clicks. That is a libinput problem, not another SPI race.

### What was already on

```
libinput Disable While Typing Enabled: 1
libinput Tapping Enabled: 1
libinput Click Method Enabled: 0, 1    (clickfinger)
```

Stock libinput **does** ship an applespi touchpad quirk (`MatchVendor=0x06CB`,
`ModelAppleTouchpad=1`, `AttrPalmSizeThreshold=1600`). Palm-*size* filtering was
therefore already attempted. Disable-while-typing was not.

### Why DWT did nothing

libinput only mutes the pad for keyboards marked **internal**. The stock quirk that
would do that:

```
[Apple Internal Keyboard (SPI)]
MatchUdevType=keyboard
MatchBus=spi
MatchVendor=0x05AC
AttrKeyboardIntegration=internal
```

This keyboard is `Apple SPI Keyboard` on SPI with **vendor/product `0000/0000`**,
so that section never matches. The generic keyboard quirks only mark PS/2 internal
and Bluetooth external. SPI is neither.

Confirmed live:

```
ID: Bus=001c Vendor=0000 Product=0000   # keyboard
ID: Bus=001c Vendor=06CB Product=0417   # touchpad  (udev: 112x69 mm)
```

xinput saying DWT is enabled is therefore misleading — the property is on, but there
is no internal keyboard to pair with.

`libinput-tools` was not installed, so `libinput quirks list` could not be used
during the first look. It is installed now.

A separate, milder mismatch: the stock pad quirk uses `AttrSizeHint=104x75` against
a device udev measures as **112×69 mm**, which skews the millimetre conversion used
for palm size.

Xorg has also logged `kernel bug: Touch jump detected and discarded` on this pad
(rate-limited after 5 messages). That is applespi injecting a jump; libinput drops
it. Not the same as a palm click.

### The fix

[`config/libinput/local-overrides.quirks`](../config/libinput/local-overrides.quirks)
is copied to `/etc/libinput/local-overrides.quirks` (libinput loads that path last;
package updates do not overwrite it):

- Mark `Apple SPI Keyboard` as `AttrKeyboardIntegration=internal`.
- Set the pad `AttrSizeHint=112x69` to match udev. **Do not** change
  `AttrPalmSizeThreshold` without a `libinput debug-events` trace that shows the
  stock 1600 is wrong.

```bash
sudo bin/input-install
```

`libinput quirks list` sees the new attributes immediately. **Xorg only reapplies
them when it reopens the devices — log out once.** Replug does not apply: these
are built-in.

Verify after logout:

```bash
bin/input-check
libinput quirks list /dev/input/event4   # want AttrKeyboardIntegration=internal
```

To undo, delete `/etc/libinput/local-overrides.quirks` and log out again.

### Ruled out / not done

- **Tapping off** as a substitute for palm rejection. The Mac clickpad should tap.
  Fix the pairing instead.
- **Touchegg / 3-finger gestures.** Not installed; not started.
- **Fn mode** is `applespi.fnmode=1` (media keys first, hold Fn for F-keys). The
  keyboard-backlight keys work on that mapping — leave it.
- **Force Touch / haptic click.** There is no Linux haptic actuator path for this
  pad. Clickfinger (two-finger right-click) is the libinput default and is what is
  on.
