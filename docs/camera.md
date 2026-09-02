# Camera — FaceTime HD on the 12-inch MacBook

**Status: WORKING on 7.0.** Confirmed 2026-09-01 after reboot with
`intel_iommu=off` on the cmdline. `/dev/video0` is **Apple Facetime HD**,
YUYV 848×588 @ 30 fps. GStreamer pulled 5 frames (4986240 bytes) with **0
SIF errors**. Chrome on the same box shows **848×588 at ~30 fps** via
[`camera-test/`](../camera-test/).

---

## Why camera was done first

Bluetooth on this machine is not a missing firmware file. The BCM4350 UART is
shared with an SSD debug port (`SSDC`). Linux serdev binds `SSDC` first and the
real Bluetooth device never appears. The known fix is a DSDT override. The
published scripts wire that into **GRUB**, which is not on this boot path
([boot.md](boot.md)). Camera was a DKMS module plus one kernel argument that
OpenLinuxBoot already knew how to read. The GRUB-free initrd path is now in
[bluetooth.md](bluetooth.md).

## Hardware

| | |
|---|---|
| PCI | `02:00.0` Broadcom FaceTime HD **`14e4:1570`** |
| Sensor | Broadcom **1675** — native **848×588**, not 720p |
| Interface | PCIe ISP, not UVC / not USB |
| In-tree driver | none bound (`bdc_pci` is a stub that must stay blacklisted) |
| `/dev/video0` | **Apple Facetime HD**, `81:0`, group `video`, udev `uaccess` |

Confirmed live:

```
02:00.0 Multimedia controller [0480]: Broadcom Inc. and subsidiaries
        720p FaceTime HD Camera [14e4:1570]
        Kernel driver in use: facetimehd
        Kernel modules: facetimehd
```

The "720p" name is Apple's. The 12-inch sensor is 848×588. That mismatch is
why every earlier Linux attempt on this chassis ended in a black frame.

## What was already known (not re-tried)

The working write-up is
[thomas-shirley/macbook8.1-camera](https://github.com/thomas-shirley/macbook8.1-camera).
The same geometry + framerate patches were merged to
[patjak/facetimehd](https://github.com/patjak/facetimehd) as PR 327
(2026-06-26). We are using the MacBook8,1 repo because it also has the
firmware extract and the IOMMU note.

| Suspect | Verdict (from that work, not re-run here) |
|---|---|
| Missing `1675_01XX.dat` calibration | Red herring. Optional colour/exposure, applied after frames flow |
| `Failed to lock S2 PLL: 0xc902c902` | Cosmetic; the lock-bit poll is inverted |
| Buffer allocation | `REQBUFS`/`STREAMON` succeed; not the SIF fault |
| Hardcoded 1280×720 crop | **The actual bug.** Commanding an 848×588 sensor to 720p produces `SIF errors: sifIrq = 0x804` on every frame |

`intel_iommu=off` is required for the ISP's DMA command channel. It is a
separate prerequisite, not the streaming bug.

## What this session did

1. Confirmed `14e4:1570` present, no driver, no `/dev/video*`, no
   `/lib/firmware/facetimehd`.
2. Cloned the camera repo to `/home/cobo/src/macbook8.1-camera`.
3. Extracted Apple firmware **1.43.0** from the El Capitan 10.11.5 driver
   (`sha256 e3e6034a67dfdaa27672dd547698bbc5b33f47f1fc7f5572a2fb68ea09d32d3d`).
4. Compiled `facetimehd.ko` against `linux-headers-7.0.0-30-generic`. It
   builds. BTF generation is skipped (no `vmlinux`) — same as other OOT
   modules here; not a problem.
5. User ran `bin/camera-install` and rebooted.
6. OpenLinuxBoot **did** pick up `GRUB_CMDLINE_LINUX_DEFAULT`:
   `/proc/cmdline` is `... ro intel_iommu=off`. `DMAR: IOMMU disabled`.
   The `config.plist` `autoopts` fallback was not needed.
7. Stream test (no `v4l-utils`; used `gst-launch-1.0` already on the box):

```
gst-launch-1.0 v4l2src device=/dev/video0 num-buffers=5 \
  ! video/x-raw,format=YUY2,width=848,height=588,framerate=30/1 \
  ! filesink location=/tmp/cam.raw
# 4986240 bytes = 5 * 848 * 588 * 2
# dmesg: New Output config -> size = 848x588
# SIF errors: 0
```

GStreamer did not stall after one frame, so the 30 fps metadata fix is live
too. Chrome later showed the same 848×588 / ~30 fps verdict on
`http://127.0.0.1:8765/`. The picture is a real exposure (dark/noisy in
low light). Missing `1675_01XX.dat` is still only calibration — it does
not block the stream.

`Failed to lock S2 PLL: 0xc902c902` still prints at probe; DDR verifies
immediately after, as expected.

## One client at a time

`facetimehd` is exclusive. A second `getUserMedia` fails with
`NotReadableError: Could not start video source` even after Chrome has
permission, and the green LED stays on. `fuser /dev/video0` showed Cursor's
embedded browser holding the node from the earlier in-IDE test. Close that
tab (or any other consumer) and retry. The test page now explains this
error and lists the device via `enumerateDevices` even when start fails.

## Install

Snapshot first, then the script. The script copies firmware, registers the
DKMS module, and adds `intel_iommu=off` to `GRUB_CMDLINE_LINUX_DEFAULT`.
`update-grub` is deliberately **not** run — GRUB is not in the boot path.
OpenLinuxBoot reads `/etc/default/grub` when `/boot` lives on the root
filesystem. **Confirmed 2026-09-01** — after install, `/proc/cmdline`
gained `intel_iommu=off` with no `config.plist` change. `update-grub` was
not run. To reinstall:

```
sudo timeshift --create --comments "before facetimehd camera DKMS"
sudo /home/cobo/mintbook/bin/camera-install
sudo reboot
```

After reboot:

```
cat /proc/cmdline    # must contain intel_iommu=off
bin/camera-diag
```

The `config.plist` `autoopts+="intel_iommu=off"` fallback is unused. The
upstream `enable-iommu-off.sh` also calls `update-grub`; skip it.

## Test once `/dev/video0` exists

Expected format is **YUYV 848×588 @ 30 fps** (997248 bytes/frame).

```
sudo apt install -y v4l-utils
v4l2-ctl -d /dev/video0 --list-formats-ext
v4l2-ctl -d /dev/video0 --stream-mmap --stream-count=5 --stream-to=/tmp/cam.raw
stat -c %s /tmp/cam.raw    # expect 4986240 (5 * 848 * 588 * 2)
```

SIF error count in `dmesg` must be **0**. A black/green picture plus
`sifIrq = 0x804` means the unpatched 1280×720 path is running.

PipeWire/WirePlumber should pick the node up for browsers once the stream
is healthy. `gst-launch-1.0` is already installed if you would rather not
add `v4l-utils`.

A one-page browser tester is in [`camera-test/`](../camera-test/):

```
bin/camera-test          # http://127.0.0.1:8765/  (needs localhost, not file://)
```

Confirmed in Chrome: **Apple FaceTime HD**, **848×588**, **~30 fps**,
verdict good. Needs `http://127.0.0.1` — `file://` cannot call
`getUserMedia`. **1280×720** means the unpatched driver is loaded. If
Chrome has permission but no picture, see [One client at a time](#one-client-at-a-time).

## Rollback

```
sudo dkms remove -m facetimehd -v 0.7.0.1 --all
sudo rm -rf /usr/src/facetimehd-0.7.0.1 /lib/firmware/facetimehd
# restore the newest /etc/default/grub.bak-* if you want IOMMU back on
```

6.14 remains the OpenCanopy fallback if 7.0 will not boot. The camera DKMS
will not build there (no headers), same as the speaker module.

## Source used

| | |
|---|---|
| Tree | `/home/cobo/src/macbook8.1-camera` |
| Driver | `bcwc_pcie/` (`facetimehd` 0.7.0.1) |
| Firmware extract | `facetimehd-firmware/` → Apple 10.11.5, firmware 1.43.0 |
