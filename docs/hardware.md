# Hardware status

What works, what does not, and what was measured. Regenerate the live parts with
[`bin/hw-report`](../bin/hw-report).

| | |
|---|---|
| Model | **MacBook8,1** — MacBook (Retina, 12-inch, Early 2015), `Mac-BE0E8AC46FE800CC` |
| Chassis | Apple **A1534** (shared with MacBook9,1 and 10,1 — relevant to [audio.md](audio.md)) |
| CPU | Intel **Core M-5Y31** @ 0.9GHz base / 2.4GHz turbo — 2 cores, 4 threads, **fanless** |
| GPU | Intel HD Graphics 5300 |
| RAM | 7.7 GB — **no swap configured** |
| Storage | 233.8 GB NVMe |
| Display | eDP-1, 2304x1440 in 259x162mm — **~226 DPI** |
| Audio controller | PCI `00:1b.0` (Wildcat Point-LP), codec Cirrus **CS4208** |
| Wireless | Broadcom **BCM4350** (`brcmfmac`) |

## Status matrix

| Device | State | Notes |
|---|---|---|
| Display / HiDPI | **Working** | Needs manual scaling, see [display.md](display.md) |
| Wi-Fi | **Working** | `brcmfmac`, associates and resolves normally |
| **Bluetooth** | **Not present** | No adapter at all — see below |
| Internal speakers | **Working on 7.0** | [audio.md](audio.md) — CS4208 TDM, clock latch fix |
| Headphone jack | **Working** | The analog path in the codec is healthy |
| Microphone | Working | `Mic=0x18`, `Internal Mic=0x19` |
| Keyboard / trackpad | **Intermittent — fixable** | Boot race, hits **both** kernels, see [input.md](input.md) |
| Battery | Working | ~84% of design capacity |
| Webcam | **Working on 7.0** | FaceTime HD `14e4:1570`, 848×588; `intel_iommu=off`; one client at a time — [camera.md](camera.md) |
| Secure Boot | Not supported | Unsigned DKMS modules load without signing |

## Bluetooth is absent, not broken

Worth stating plainly — it is not a fallback if the built-in speakers or jack
fail:

```
/sys/class/bluetooth/     empty
rfkill list               only "phy0: Wireless LAN"
bluetoothctl list         nothing
```

The `bluetooth`, `btbcm`, `btintel` and `hci_uart` modules are all loaded and the
`bluetooth.service` is active — there is simply **no adapter for them to bind to**.
The BCM4350's Bluetooth side needs Apple firmware that is not present. This is a
known, separate MacBook-on-Linux problem and has not been attempted.

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

## No swap

7.7 GB with no swap at all. With Electron apps and Firefox on a Core M this is a real
risk of hard OOM rather than gradual slowdown. `zram-config` would be the cheap fix
(compressed swap in RAM, no NVMe wear). **Not done** — flagged only.

## Base toolchain

Present on a stock install: `git`, `python3` (3.12), `gcc`, `make`, `curl`, `dkms`,
`timeshift`, kernel headers for **7.0.0-30-generic**.

**Absent:** `node`, `npm`, `jq`, `gh`, `docker`, `rustc`, `go`, `java`. Claude Desktop
is installed as a `.deb` and bundles its own runtime under
`/usr/lib/claude-desktop`, which is why it runs with no system Node present.

Screenshot tooling is **`xfce4-screenshooter` only** — no `scrot`, `maim` or `import`.
