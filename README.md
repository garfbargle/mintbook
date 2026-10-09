<div align="center">

# mintbook

### The 12-inch MacBook. Reimagined for Linux.

Quiet by design. Familiar at first glance. Built for the hardware underneath.

</div>

<p align="center">
  <img src="docs/images/spotlight.jpg" alt="Overview open on the mintbook desktop" width="880">
</p>

<p align="center">
  <strong>MacBook8,1 · Early 2015 · fanless Core M · 2304 × 1440</strong><br>
  Linux Mint 22.3 · XFCE · kernel 7.0
</p>

This is one machine, documented: the desktop work and the hardware fixes that
make a 2015 MacBook worth carrying in 2026. It is a reference rather than a
distribution—there is no one-command install, and the measurements are the
point at least as much as the theme. Take what is useful.

## It feels like it belongs.

Mintbook turns the 12-inch MacBook into a focused Linux machine—without turning
Linux into a macOS costume. No Apple logo. No blur. Just a crisp glass bar, a
dock, and the controls you reach for every day.

<p align="center">
  <img src="docs/images/desktop.jpg" alt="The mintbook desktop at rest" width="48%">
  &nbsp;
  <img src="docs/images/files.jpg" alt="Files on the mintbook desktop" width="48%">
</p>

The machine looks like itself before you log in, too. The greeter wears the
session's theme, font, wallpaper and cursor size, with the hostname and the
keyboard indicator taken off it—and since the lock screen is that same program,
it is the surface you meet every time the lid opens. **Login Screen** picks the
picture it shows: every wallpaper already on the disk, or one of your own,
which it copies somewhere the greeter can actually read.

Click the search icon at the far right of the bar—or press **Cmd+Space**.
Overview finds applications and system actions together, in one fast surface,
and follows the appearance you are in.

<p align="center">
  <img src="docs/images/spotlight-light.jpg" alt="Overview in the light appearance" width="48%">
  &nbsp;
  <img src="docs/images/spotlight-dark.jpg" alt="Overview in the dark appearance" width="48%">
</p>

**Show All Applications** opens a full-screen grid built for the display. Start
typing and your first keystroke flows straight into Overview. No second search.
No starting over.

<p align="center">
  <img src="docs/images/app-grid.png" alt="Show All Applications on Mintbook" width="880">
</p>

**Cmd+Left/Right** places windows. **Cmd+Shift+3** takes a screenshot. The
familiar gestures are simply there.

## Everything you need. Nothing you don't.

The bar shows what matters: performance, temperature, connectivity, battery,
and time. Everything it controls lives in one place.

<p align="center">
  <img src="docs/images/control-center.jpg" alt="Mintbook Control Center" width="340">
</p>

Control Center is fast, keyboard-friendly, and intentionally small. Behind it
are eleven simple executables—not a permanent background service. Adding a tile
takes about twelve lines.

Wi-Fi, Bluetooth, battery, and CPU open directly from the bar. Updates appear only
when updates exist, with apt and Flatpak together in one clean list.

<p align="center">
  <img src="docs/images/wifi-menu.jpg" alt="Wi-Fi menu" width="31%">
  &nbsp;
  <img src="docs/images/bluetooth-menu.jpg" alt="Bluetooth menu" width="31%">
  &nbsp;
  <img src="docs/images/battery-menu.jpg" alt="Battery menu" width="31%">
</p>

## Send it to the machine next to you.

Drag files onto the Mintdrop icon in the dock, or right-click them in Files
and choose **Send with Mintdrop**. A sheet opens with the devices that are
nearby, as circles you can let go of a file on. The transfer happens on the
tile—a ring closing around the device you sent to—rather than in a dialog
somewhere else.

<p align="center">
  <img src="docs/images/mintdrop-sheet-light.png" alt="The Mintdrop sheet in the light appearance, showing a nearby phone as a round tile" width="239">
  &nbsp;
  <img src="docs/images/mintdrop-sheet-dark.png" alt="The same sheet in the dark appearance" width="232">
</p>

Anything arriving here says so first. Who is sending, what it is, how big,
and from which address—and the default answer is no. Escape declines, a
prompt nobody answers declines, and a sender that cannot be shown a prompt
is declined too.

<p align="center">
  <img src="docs/images/mintdrop-accept-light.png" alt="The Mintdrop prompt in the light appearance: Galaxy S24 wants to send you a file, with Decline and Accept" width="283">
  &nbsp;
  <img src="docs/images/mintdrop-accept-dark.png" alt="The same prompt in the dark appearance" width="283">
</p>

**It costs nothing while you are not using it.** There is no daemon and no
timer: the kernel holds the listening socket, and systemd starts a receiver
only at the moment a connection arrives. Being discoverable is one static
file read by the Avahi daemon that is already running for the rest of the
system. A file that is landing runs niced and in the idle I/O class, so an
arriving gigabyte cannot stall the desktop on two cores.

**It sends to Android phones.** Not a fallback or a web page—real Quick
Share, Google's own handshake, against an unmodified phone with nothing
installed on it. Pick the phone in the sheet, tap Accept on its screen, and
the file is there. Bluetooth has to be on: Android sleeps its Nearby stack to
save battery, and a BLE advertisement is what wakes it. Receiving from Android
is supported too, with confirmation before saving.

This is not Apple's AirDrop, and on this machine it cannot be: AirDrop puts
its data on AWDL, which needs the wireless card in monitor mode with frame
injection, and the BCM4350 here has neither. Quick Share—Samsung's and
Google's—announces over BLE and mDNS and then moves bytes over an ordinary
TCP connection, which any card can do. That is the shape Mintdrop follows,
and the reason it works here at all.

[How it works, and what it does not protect](docs/mintdrop.md)

## Tuned by evidence.

This is more than a desktop theme. It is the hardware work that makes this
particular MacBook worth using again.

- Wi-Fi, speakers, headphones, camera, Bluetooth, keyboard, and trackpad work.
- Battery mode stays cool; external power unlocks short bursts of performance.
- Suspend uses the mode that reliably brings the keyboard and trackpad back.
- Hibernation works on battery. Two days of failed restores narrowed it to one
  driver that could not come back from an image saved on battery—the Broadcom
  Wi-Fi. It now steps aside for the hibernate step and returns after. On
  battery, closing the lid sleeps, then hibernates after 30 minutes, so a night
  unplugged no longer drains the pack. [How it was found](docs/hibernate.md)
- Firefox hardware-decodes H.264 for smooth, efficient video.

Three results from that work, each measured on this machine rather than reasoned
about:

| | before | after | |
|---|---:|---:|---|
| Raw `getpid` syscall | 720 ns | **127 ns** | CPU mitigations off—a security trade with a number attached, not a free win |
| The status bar | 20.4% | **5.6%** | of one core. The most expensive software on the machine was the thing drawing six glyphs |
| `panel-power` | 357 ms | **33 ms** | it was starting a Python interpreter in order to fork a second one |

Every tuning decision is measured, documented, and reversible. The surprises
are recorded too—including the popular tweaks that made no difference.

`bin/doctor` re-checks every fragile piece, read-only and without sudo. A kernel
or Mint update is exactly what quietly removes one of them, so it is worth
running after every one. This is a real run, excerpted—the counts are the whole
machine:

<p align="center">
  <img src="docs/images/doctor.svg" alt="bin/doctor output across the kernel, graphics, audio, camera and Bluetooth sections, ending 83 ok, 2 warn, 0 FAIL" width="880">
</p>

The same run has a window. **Doctor** lives in the System tray menu and in
Overview: the tray shows the passed, note and error counts at a glance; click
a count for the matching findings. The full view groups them the way
`doctor` groups them, and—when something is wrong—the repair command sitting
right under the finding, one click from your clipboard. A warning is not a
failure here, and the card does not pretend otherwise.

<p align="center">
  <img src="docs/images/health.jpg" alt="The System Health window listing checks by section, with a summary card reading Everything checks out, 83 passed and 2 notes" width="760">
</p>

[See the measurements](docs/performance.md) · [See how fast it feels](docs/feel.md) · [See hardware status](docs/hardware.md)

## Built all the way through.

| | |
|---|---|
| **Desktop** | [Look and behavior](docs/desktop.md) · [Control Center and System menu](docs/control-center.md) · [Software updates](docs/updates.md) · [HiDPI display](docs/display.md) · [Login and lock screen](docs/login.md) |
| **Daily use** | [Shortcuts and search](docs/daily.md) · [Battery](docs/battery.md) · [Video](docs/video.md) · [Nearby sharing](docs/mintdrop.md) |
| **Hardware** | [Input and sleep](docs/input.md) · [Hibernation](docs/hibernate.md) · [Audio](docs/audio.md) · [Camera](docs/camera.md) · [Bluetooth](docs/bluetooth.md) |
| **System** | [Boot and kernels](docs/boot.md) · [App performance](docs/app-performance.md) · [Top-bar review](docs/top-bar-review.md) · [Implementation guide](CONTRIBUTING.md) |

macOS remains on the disk. OpenCore chooses which system boots; GRUB does not.
Kernel 6.14 remains a bootable fallback, though speakers, camera, and Bluetooth
require kernel 7.0 on this machine.

## Make a change. Keep a way back.

Before any system-level change:

```bash
sudo timeshift --create --comments "before <change>"
```

Installers print their own undo instructions. `bin/overview-install` adds the
Overview bar icon and shortcut; its `--revert` removes the icon while preserving
the established shortcut. Daily conveniences can be added or removed with
`bin/daily-install` and `bin/daily-install --revert`. The original XFCE desktop
can always be restored with `bin/revert-mac-theme`.

Nothing here asks you to trust a tweak you cannot inspect—or keep a change you
cannot undo.

## License and upstream work

Mintbook is available under the [MIT License](LICENSE). Small upstream sources
that Mintbook directly adapts are preserved under [`vendor/`](vendor/README.md),
with their original licenses and exact source revisions listed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
