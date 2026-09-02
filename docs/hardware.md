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
| Battery | Working | ~84% of design capacity |
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
| Health | **~84%** of design (34.2 Wh of 40.3 Wh) |
| Cycles | 147 |

Good for a machine of this age. Read it with:

```bash
upower -i /org/freedesktop/UPower/devices/battery_BAT0
```

> `/sys/class/power_supply/BAT0/capacity` is the **charge** percentage;
> `upower`'s `capacity:` field is **health**. They are different numbers and are easy
> to confuse.

## Thermals

The CPU is fanless and thermally limited — it throttles rather than spinning up a fan.
Idle has been measured around 60°C, and 73-88°C during sustained desktop work
(`high`/`crit` are both 95°C). Avoid anything with a continuous CPU or GPU cost.

```bash
sensors        # lm-sensors is installed
```

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
([desktop.md](desktop.md)).
