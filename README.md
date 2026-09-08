# mintbook

The 12-inch MacBook, on Linux Mint.

Looks like macOS. Works like it should.

<p align="center">
  <img src="docs/images/desktop.jpg" alt="mintbook desktop" width="880">
</p>

MacBook8,1 · Early 2015 · fanless Core M · 2304×1440
Linux Mint 22.3 · XFCE · kernel 7.0
macOS is still on the disk. OpenCore chooses what boots.

## The look

No Apple logo. No blur. A 52px glass bar, a dock, and Cmd+Space.

<p align="center">
  <img src="docs/images/files.jpg" alt="Files" width="48%">
  &nbsp;
  <img src="docs/images/spotlight.jpg" alt="Spotlight" width="48%">
</p>

The bar keeps what you read — CPU, temperature, Bluetooth, Wi-Fi, battery, the clock.
Everything you *set* is one click away, in a Control Center that is nine small
executables in a directory. Adding a tile is a twelve-line file.

<p align="center">
  <img src="docs/images/control-center.jpg" alt="Control Center" width="340">
</p>

Cmd+Shift+3 takes a screenshot. On battery it stays cool. Plug in, and it opens up.

When something needs updating, an arrow appears at the left of the indicators
and a Software Update panel installs them one at a time or all at once — apt
and Flatpak in the same list. When nothing does, the arrow is not there.

<p align="center">
  <img src="docs/images/updates.jpg" alt="Software Update" width="440">
</p>

Wi-Fi and Bluetooth each have a glass menu behind their icon — the networks in
range, the devices you own and what is left in them — and neither opens a
window to do it.

<p align="center">
  <img src="docs/images/wifi-menu.jpg" alt="Wi-Fi menu" width="31%">
  &nbsp;
  <img src="docs/images/bluetooth-menu.jpg" alt="Bluetooth menu" width="31%">
  &nbsp;
  <img src="docs/images/battery-menu.jpg" alt="Battery menu" width="31%">
</p>

The wiring: [desktop](docs/desktop.md) · [control center](docs/control-center.md) · [updates](docs/updates.md) · [battery](docs/battery.md) · [bluetooth](docs/bluetooth.md) · [display](docs/display.md)

## Daily shortcuts

Cmd+Space searches applications and system actions: appearance, Bluetooth,
battery history, system health, updates, and timed Keep Awake. Cmd+Left/Right
places the current window in either half of its monitor; Cmd+Down restores it.
Screenshots offer **Copy** and **Open** in their notification.

Control Center and the network, Bluetooth, battery and update menus support
Tab/Shift+Tab, arrows, Enter and Escape. Keep Awake expires automatically;
System Health explains `doctor` findings and checks after a running-kernel change.

Install or undo this set with `bin/daily-install` / `bin/daily-install --revert`.
[Details and verification](docs/daily.md) · [Implementation guide](CONTRIBUTING.md)

## Hardware

Wi-Fi, speakers, headphones, camera, Bluetooth, keyboard, trackpad.

Speakers, camera, and Bluetooth want kernel **7.0**. **6.14** is the fallback if 7.0 will not boot — silent speakers, but it boots. OpenCore is the picker. GRUB is not.

Sleep has been working in daily use over the last few days, reported on
2026-09-07. The resume hook rebinds `applespi`, which previously left the keyboard
and trackpad dead after S3. A controlled cycle/battery test is still outstanding;
see [input](docs/input.md).

`bin/hw-report` is live. Read-only. No sudo.

`bin/service-trim --check` lists the services this machine has no hardware or
no use for, and why. It needs no root and changes nothing until you run it
without `--check`.

`bin/idle-probe` measures where the idle watts go — package power, runtime PM,
framebuffer compression — and `--try` A/Bs one device and puts it back.

`bin/io-probe` measures the disk. The SSD controller here takes **one command at
a time** (`qdepth_one`), so ordinary NVMe tuning advice does not apply — see
[hardware](docs/hardware.md).

[Performance](docs/performance.md) records a tuning pass from 2026-09-04 — what
changed, what it was worth, and the six things that turned out to be wrong.

[Desktop app performance](docs/app-performance.md) records the 2026-09-06
Reduce motion change: 62% lower app CPU in the sampled active-task view,
with raw measurements, undo steps, and the next-session handoff.

[Video](docs/video.md) records the 2026-09-06 playback pass. **Watch video in
Firefox.** It hardware-decodes H.264 through the i965 driver and drops **0.2%** of
frames at 720p60. No Chromium can reach that decoder: Chrome drops **19.5%** of the
same clip, and Thorium — genuinely better, and still software — drops **2.7%** by
spending a whole core. Chrome's `chrome://gpu` claims hardware decode and is
describing the driver, not itself. Hardware H.264 *encode* is advertised by the
driver and crashes.

[Feel](docs/feel.md) asks a different question from the other passes: not how
much work the machine does, but how fast it feels. Under load the package hits
its **95 °C** limit in under three seconds and holds **1700–1900 MHz** of a
2400 MHz maximum — so the machine has about three seconds of turbo and no
sustained fast state. The battery cap costs **+36.5%** on a one-second task and
almost nothing on a long one, so `bin/turbo-budget` now gives back eight
uncapped seconds per burst and takes the cap for everything after. Background
disk traffic costs **1.8x** on a cold application read and nothing measurable on
the compositor. Key repeat was at the X11 default of 500 ms and is now 200.

Ten candidates, with where each one ended up — three of them, including one that
was already fine, turned out differently from how they were written down.

`bin/firefox-video` applies the two prefs that make YouTube serve H.264 — the one
format the GPU can decode — and `bin/firefox-video --undo` takes them back out.
Firefox needs nothing else: it hardware-decodes H.264 out of the box here.

After a kernel update, run `bin/doctor`. It checks every piece this machine needs —
firmware, DKMS modules, the DSDT override, udev and systemd units, the panel — and
tells you which one an update took away.

[Hardware](docs/hardware.md) · [Input](docs/input.md) · [Audio](docs/audio.md) · [Camera](docs/camera.md) · [Bluetooth](docs/bluetooth.md) · [Boot](docs/boot.md) · [Video](docs/video.md)

## Before you touch it

```bash
sudo timeshift --create --comments "before <change>"
```

`bin/revert-mac-theme` puts the original XFCE desktop back.

Every install script prints its own undo. So does `bin/tune-install`.

The docs record what was tried, and what was not.
