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
- **Kernel parameters are *probably* still taken from `/etc/default/grub`.** There is no
  `/etc/kernel/cmdline` and no `/boot/loader/entries/`, so OpenLinuxBoot is in
  autodetect mode, where it falls back to reading `GRUB_CMDLINE_LINUX_DEFAULT` /
  `GRUB_CMDLINE_LINUX`. Both are currently empty, which matches the bare command line
  observed. **Unverified** — if you need a kernel argument, set it there, reboot, and
  confirm it actually shows up in `/proc/cmdline` before trusting it. Prefer fixes that
  need no kernel argument at all; see [input.md](input.md).

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
| `7.0.0-30-generic` | Current default. Ubuntu HWE (`linux-hwe-7.0`). |
| `6.14.0-37-generic` | **Also fine.** Kernel binary untouched since 2025-11-20. |

**Both kernels work.** An earlier version of this document claimed 6.14 had no working
keyboard or trackpad — **that was wrong**, and it was wrong in a way worth
understanding: it was a sample of two bad boots. The keyboard/trackpad failure is an
intermittent boot race that hits **both** kernels at roughly the same rate. See
**[input.md](input.md)** — that is the doc that matters here.

Do not conclude a kernel is broken from a single bad boot on this machine. Check
`bin/input-check` first.

### Do not let DKMS build for 7.0

The out-of-tree audio driver **panics at probe on 7.0** and takes the analog card down
with it. Its `dkms.conf` sets `AUTOINSTALL="yes"`, so it rebuilds itself for every
newly installed kernel. If it is installed for 6.14, check for and remove any 7.0
build:

```bash
dkms status
sudo dkms remove -m macbook12-audio-driver -v 0.1 -k 7.0.0-30-generic
```

---

## Rollback safety

Both kernels stay installed and selectable from the OpenCore picker, so a bad kernel is
never a dead end. `timeshift` is installed; snapshot before anything touching kernels
or modules:

```bash
sudo timeshift --create --comments "before <change>"
```
