# mintbook

Running **Linux Mint on a 2015 12-inch MacBook** — making it look like macOS, and
making the hardware work.

This repo is the record of that work. It exists so a future session with **no prior
context** can understand what was changed, why, what was already tried, and what was
ruled out. Where something is unsolved it says so, with the evidence, so the same
ground is not covered twice.

---

## The machine

**MacBook8,1** (Retina, 12-inch, Early 2015) — fanless Core M-5Y31, 7.7 GB RAM,
2304x1440 at ~226 DPI, running **Linux Mint 22.3 "Zena"** (Ubuntu 24.04 base) on
**XFCE 4.18 / X11**. It dual-boots macOS, which is still installed on the same disk.

Full detail and the live report: [docs/hardware.md](docs/hardware.md).

## Status at a glance

| | |
|---|---|
| macOS-style desktop | **Done** — [docs/desktop.md](docs/desktop.md) |
| HiDPI scaling | **Done** — [docs/display.md](docs/display.md) |
| Wi-Fi, headphones, speakers, battery, display | **Working** — speakers need kernel **7.0**, see [docs/audio.md](docs/audio.md) |
| **Keyboard/trackpad** | **Working** — DMA blacklist + DWT quirk; log out once for DWT — [docs/input.md](docs/input.md) |
| **Bluetooth** | **Working on 7.0** — [docs/bluetooth.md](docs/bluetooth.md) |
| **Webcam** | **Working on 7.0** — [docs/camera.md](docs/camera.md) |
| Boot chain | **OpenCore loader; GRUB is inert** — [docs/boot.md](docs/boot.md) |

## Documentation

Read in this order if you are new to the machine:

| Doc | Covers |
|---|---|
| [docs/input.md](docs/input.md) | **Read first.** SPI boot race (fixed) and palm / disable-while-typing |
| [docs/hardware.md](docs/hardware.md) | What the machine is; per-device working/broken matrix; battery, thermals, toolchain |
| [docs/boot.md](docs/boot.md) | Disk layout, dual-boot, why GRUB is **not** in the boot path, kernel 7.0 |
| [docs/display.md](docs/display.md) | HiDPI scaling — why it is split between window scale and font DPI |
| [docs/desktop.md](docs/desktop.md) | The macOS look: top bar, dock, Spotlight, WM, panel indicators, and its gotchas |
| [docs/audio.md](docs/audio.md) | CS4208 speakers — what was ruled out, the 7.0 DKMS fix, PipeWire routing |
| [docs/camera.md](docs/camera.md) | FaceTime HD (`14e4:1570`) — 848×588 sensor, DKMS, `intel_iommu=off` |
| [docs/bluetooth.md](docs/bluetooth.md) | BCM4350 UART — SSDC serdev conflict, DSDT override on the 7.0 initrd; **working** |

## Repo layout

```
bin/                    scripts; mirrors ~/.local/bin/
  audio-diag            dump the full audio/codec state       (read-only)
  camera-diag           FaceTime HD PCI/firmware/IOMMU state  (read-only)
  camera-install        firmware + facetimehd DKMS + iommu=off (root)
  camera-test           local page to preview the FaceTime HD camera
  bt-diag               Bluetooth / SSDC-UART state           (read-only)
  bt-install            DSDT override + 7.0 initrd prepend    (root)
  hw-report             live hardware status                  (read-only)
  input-check           SPI keyboard/trackpad PIO + DWT quirk check (read-only)
  input-install         libinput DWT quirk + DMA blacklist (root)
  hda-dump              HDA verb dump (root; historical)
  hda-enable-digen      enable CS4208 Digital Convert (root; historical)
  hda-gpio-sweep        GPIO/DigEn sweep during playback (root; ruled out)
  mb81-jack-switch      headphone jack auto-switch (user systemd override)
  codec-snapshot        capture codec state to diff
  spotlight             Cmd+Space launcher toggle
  screenshot            save a png (no dialog); Cmd+Shift+3/4/5
  panel-cpu             genmon CPU sparkline
  panel-temp            genmon CPU temperature
  panel-wifi            genmon Wi-Fi indicator
  panel-bt              genmon Bluetooth indicator
  revert-mac-theme      restore XFCE config from the backup
config/initramfs/       post-update hook that prepends the BT DSDT override
config/libinput/        local-overrides.quirks (DWT / palm size hint)
config/systemd/         zram-generator.conf (compressed swap)
config/pipewire/        WP 0.4 raw-speaker adapter (copy to ~/.config/pipewire/pipewire.conf.d/)
config/plank/           dock launcher definitions
config/rofi/            rofi config + Spotlight theme
config/xfce4-panel/     genmon rc files (genmon does NOT use xfconf)
icons/                  icon generators (wifi, bluetooth)
settings/               xfconf + dconf dumps (reference snapshots)
camera-test/            local FaceTime HD browser preview (bin/camera-test)
docs/                   see above
```

`~/.local/bin` is on PATH via `~/.profile`, but only from the next login after it was
first created.

## Conventions used here

- **Diagnostics before claims.** `bin/audio-diag` and `bin/hw-report` are read-only and
  need no sudo. Run them rather than trusting a value quoted in a doc — the docs record
  what was true when written.
- **Every doc states what was *ruled out*,** not just what worked. That is usually the
  more valuable half.
- **Nothing here needs sudo except kernel-module and package work,** and those steps are
  written out explicitly rather than run silently.

## Before changing anything risky

Daily kernel is **7.0** (speakers need it). **6.14** stays installed as the
normal fallback if 7.0 will not boot — speakers are silent there. OpenLinuxBoot,
not GRUB, is the picker — see [docs/boot.md](docs/boot.md). For anything
touching modules or packages, snapshot first:

```bash
sudo timeshift --create --comments "before <change>"
```

The original XFCE config, saved before any of the desktop work, is in
`~/mac-mint-backup-20260831-224309/`; `bin/revert-mac-theme` restores it.
