# Boot, firmware and kernels

> The boot chain is now confirmed: **OpenCore is the loader.** The ESP layout below was
> read directly. What remains unread is `config.plist` itself — see the TODO at the end
> of that section.

---

## Disk layout

This is a **dual-boot machine — macOS is still installed.**

```
nvme0n1     233.8G
├─nvme0n1p1   300M  vfat   /boot/efi     EFI system partition
├─nvme0n1p2 159.1G  apfs                 macOS  (not mounted under Linux)
└─nvme0n1p3  74.3G  ext4   /             Linux Mint
```

| | |
|---|---|
| Root filesystem UUID | `7e20499d-3977-4253-9dfc-590530d5b1fe` |
| Root **PARTUUID** | `bad575a6-289c-4697-a610-0fd3a3dfd617` (this is what actually boots it) |
| Firmware | EFI |
| Apple BIOS version | `481.0.0.0.0`, dated 2023-01-12 |
| Secure Boot | **Not supported** — unsigned kernel modules load freely |

---

## The boot chain: OpenCore, not GRUB

**This is the thing to understand before changing any boot setting.**

```
Apple EFI firmware
  -> Boot0080 "EFI"  (\System\Library\CoreServices\boot.efi on the ESP)
  -> OpenCore        (EFI/OC/OpenCore.efi, GUI picker via OpenCanopy)
  -> OpenLinuxBoot   (scans ext4, boots the kernel directly via EFISTUB)
  -> kernel
```

GRUB is installed but **is not in this path**.

### ESP layout

```
/boot/efi/EFI/
├── APPLE/          Apple firmware + SMC updaters (stock, leave alone)
├── BOOT/           BOOTX64.EFI, fbx64.efi, mmx64.efi
├── OC/             OpenCore
│   ├── config.plist
│   ├── config.plist.bak-ext4-1446      <- prior experiment
│   ├── config.plist.bak-shim-1505      <- prior experiment
│   ├── Drivers/    Ext4Dxe, OpenCanopy, OpenLinuxBoot, OpenRuntime, ResetNvramEntry
│   ├── Kexts/      macOS-side only (Lilu, AirportBrcmFixup, AppleHSSPI*, ...)
│   ├── Tools/      BootKicker.efi, OpenShell.efi
│   └── Resources/  OpenCanopy icons/fonts (Acidanthera GoldenGate)
└── ubuntu/         grubx64.efi, shimx64.efi, grub.cfg
                    + grub.cfg.orig, grub.cfg.claude-minimal   <- modified
```

**`OpenLinuxBoot.efi` + `Ext4Dxe.efi` is the mechanism.** OpenLinuxBoot reads the ext4
root directly, finds the kernels in `/boot`, and boots them EFISTUB — no bootloader on
the Linux side involved. That is exactly why the command line looks like this:

```
$ cat /proc/cmdline
initrd=\boot\initrd.img-7.0.0-30-generic root=PARTUUID=bad575a6-... ro
```

EFI backslash paths and `root=PARTUUID=`, which GRUB would never emit. And why NVRAM
holds no Linux entry at all:

```
$ efibootmgr
BootOrder: 0080
Boot0080* EFI       ...\System\Library\CoreServices\boot.efi
Boot0081* Mac OS X  ...
Boot0082*           ...
```

"Select EFI, then EFI again" is the **firmware picker** followed by **OpenCanopy**,
OpenCore's own graphical picker.

### What this means in practice

- **`update-grub` does nothing** for how this machine boots. Kernel entries come from
  OpenLinuxBoot scanning `/boot`, so a newly installed kernel appears automatically.
- **Kernel selection is OpenCore's**, in the OpenCanopy picker.
- **Kernel parameters are taken from `/etc/default/grub`.** There is no
  `/etc/kernel/cmdline` and no `/boot/loader/entries/`, so OpenLinuxBoot is in
  autodetect mode and reads `GRUB_CMDLINE_LINUX_DEFAULT` / `GRUB_CMDLINE_LINUX`
  (documented by OpenLinuxBoot for Debian/Ubuntu with `/boot` on the root fs).
  Both were empty, which matched the bare command line. **Confirmed
  2026-09-01:** writing `intel_iommu=off` into
  `GRUB_CMDLINE_LINUX_DEFAULT` (no `update-grub`) made it appear on
  `/proc/cmdline` after reboot. The `config.plist` `autoopts` fallback was
  not needed. Prefer fixes that need no kernel argument at all; see
  [input.md](input.md).
- **Early initrd is not a GRUB feature here.** OpenLinuxBoot passes one
  `initrd=` path. The Bluetooth DSDT override is prepended to that file
  (`/boot/initrd.img-7.0*`) by `bin/bt-install` and an
  `update-initramfs` post-update hook. `GRUB_EARLY_INITRD_LINUX_CUSTOM`
  is unused. 6.14's initrd is left stock as the ACPI fallback. See
  [bluetooth.md](bluetooth.md).

### The bare `grub>` prompt

`EFI/ubuntu/` contains `grub.cfg` alongside **`grub.cfg.orig` and
`grub.cfg.claude-minimal`** — the config there has been replaced at some point. If
OpenCore chainloads `shimx64.efi`/`grubx64.efi`, you land in a GRUB whose config is
minimal or cannot locate the real `/boot/grub/grub.cfg`, which presents as a bare
prompt instead of a menu. That is a side road; the working path is to go back to the
OpenCanopy picker and choose a kernel entry.

The two `config.plist` backups (`bak-ext4-1446`, `bak-shim-1505`) show that booting via
Ext4Dxe and via shim were both tried. The current, working arrangement is the
Ext4Dxe/OpenLinuxBoot one.

If you must hand-boot from a `grub>` prompt:

```
grub> ls
grub> ls (hd0,gpt3)/boot                     # confirm the real filenames first
grub> set root=(hd0,gpt3)
grub> linux /boot/vmlinuz-7.0.0-30-generic root=UUID=7e20499d-3977-4253-9dfc-590530d5b1fe ro
grub> initrd /boot/initrd.img-7.0.0-30-generic
grub> boot
```

**TODO:** `EFI/OC/config.plist` itself has not been read (root-only). Worth recording:
the `Misc/Entries` list, `Misc/Boot` picker settings, and OpenLinuxBoot's `Driver
Arguments`. Dump it with `sudo cat /boot/efi/EFI/OC/config.plist`.

---

## Kernels

| Kernel | Notes |
|---|---|
| `7.0.0-30-generic` | **Daily driver.** Ubuntu HWE (`linux-hwe-7.0`). Speakers only work here. |
| `6.14.0-37-generic` | **Fallback only.** Boots Linux if 7.0 is broken. Speakers will be silent. No headers, so the speaker DKMS does not build for it. |

Keeping the previous kernel is the normal Mint/Ubuntu safety net — OpenLinuxBoot
lists everything in `/boot`. Daily use stays on 7.0. Keep
`linux-image-generic-hwe-24.04` installed so apt stays on the 7.0 HWE line.

The generic `/boot/vmlinuz` symlink must point at **7.0**. Reinstalling 6.14
flips it; put it back:

```bash
sudo ln -sfn vmlinuz-7.0.0-30-generic /boot/vmlinuz
sudo ln -sfn initrd.img-7.0.0-30-generic /boot/initrd.img
sudo ln -sfn vmlinuz-6.14.0-37-generic /boot/vmlinuz.old
sudo ln -sfn initrd.img-6.14.0-37-generic /boot/initrd.img.old
```

Do not conclude a kernel is broken from a single bad boot. Check `bin/input-check`
first.

### DKMS modules

`macbook12-audio/0.1` from [thomas-shirley/macbook8.1-speaker-driver](https://github.com/thomas-shirley/macbook8.1-speaker-driver)
is installed for 7.0 (`dkms status`). It **must** be built against Ubuntu's
`linux-hwe-7.0` `sound/hda` tree, not kernel.org — kernel.org structs panic at
probe on this ABI (same trap as `leifliddy/macbook12-audio-driver`). See
[audio.md](audio.md).

`facetimehd/0.7.0.1` from [thomas-shirley/macbook8.1-camera](https://github.com/thomas-shirley/macbook8.1-camera)
is also installed for 7.0. Needs `intel_iommu=off` on the cmdline (set in
`/etc/default/grub`; OpenLinuxBoot reads it). See [camera.md](camera.md).

---

## Rollback safety

6.14 is the OpenCanopy fallback if 7.0 will not boot. macOS is still on
`nvme0n1p2`. `timeshift` is installed; snapshot before anything touching kernels
or modules:

```bash
sudo timeshift --create --comments "before <change>"
```
