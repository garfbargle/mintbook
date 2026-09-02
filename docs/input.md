# Input — the Apple SPI keyboard/trackpad race

**This is the single most important thing to know about this machine.**

The built-in keyboard and trackpad fail **intermittently at boot**, roughly half the
time. It is **not** tied to a kernel version, and it is **not** a broken install.
It is a probe-order race, and it is fixable.

---

## Symptom

Boot, and sometimes the keyboard and trackpad are simply dead. The machine looks
hung. Rebooting a few times eventually lands on a good boot. There is no pattern the
user can see, which is what makes it so unpleasant to diagnose.

## The mechanism

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

## The evidence

Every recorded boot on this machine, both kernels:

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

## The fix

Remove the race by removing the DMA provider, so SPI always falls back to PIO.
**Nothing else on this machine uses that DMA engine** — all 8 channels read
`in_use=0` even on a good boot.

```bash
sudo tee /etc/modprobe.d/blacklist-dw-dmac.conf >/dev/null <<'EOF'
# The Apple SPI keyboard/trackpad (applespi @ pxa2xx_spi_pci 00:15.4) times out on
# every DMA transfer on this hardware. Whether SPI gets DMA is a boot race against
# dw_dmac_pci; losing it leaves the machine with no keyboard or trackpad.
# Removing the DMA provider forces the working PIO path deterministically.
# Nothing else here uses this DMA engine (all channels in_use=0).
# Undo: delete this file.
blacklist dw_dmac_pci
install dw_dmac_pci /bin/false
EOF
```

**No initramfs rebuild is needed** — `dw_dmac_pci` is not in the initramfs (only the
`dw_dmac` platform variant is), so it loads after the root pivot where
`/etc/modprobe.d/` already applies.

**No GRUB change, and no kernel command line change** — see [boot.md](boot.md) for why
neither would take effect on this machine anyway.

To undo, delete the file and reboot.

### Verifying

After rebooting:

```bash
bin/input-check
```

Expect `using PIO`, zero timeouts, and both keyboard and touchpad present.

## Consequences

- **6.14 was not broken for input.** The race hits every kernel. 6.14 is kept as
  a boot fallback; speakers only work on 7.0 — see [audio.md](audio.md) and
  [boot.md](boot.md).
- This is very likely the cause of the long, miserable session of black screens and
  unresponsive boots that preceded this investigation. Combined with a boot menu that
  is easy to mis-navigate ([boot.md](boot.md)), a dead-input boot is hard to tell apart
  from a failed boot.
