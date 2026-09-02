# Input — Apple SPI keyboard and trackpad

**Status: working.** Two separate problems, both now addressed:

| | |
|---|---|
| Dead at boot | **Fixed.** `dw_dmac_pci` is blacklisted, so SPI always uses PIO. |
| Palm / typing | **Quirk installed.** Disable-while-typing was a no-op until the keyboard was marked internal. **Log out once** for Xorg to reload it. |

`bin/input-check` reports both. `sudo bin/input-install` copies the quirk (and the
blacklist, if missing).

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

## 2. Palm rejection / disable-while-typing

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
