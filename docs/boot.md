# Boot, firmware and kernels

> **Partly unverified.** The OpenCore configuration itself has not been inspected —
> the ESP is not readable without sudo. Sections marked **TODO** are the gaps.
> Everything else here is evidenced from the running system.

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

## GRUB is not in the boot path

**This is the thing to understand before changing any boot setting.**

The kernel is booted **directly (EFISTUB)**, not by GRUB. Two independent proofs:

**1. The kernel command line is not GRUB's format.**

```
$ cat /proc/cmdline
initrd=\boot\initrd.img-7.0.0-30-generic root=PARTUUID=bad575a6-... ro
```

Backslash path separators and `root=PARTUUID=`. GRUB emits forward slashes and
normally `root=UUID=`. Backslashes are the EFI path convention — this line was written
by an EFI bootloader handing the kernel straight to the firmware.

**2. There is no Linux boot entry in NVRAM.**

```
$ efibootmgr
BootOrder: 0080
Boot0080* EFI       ...\System\Library\CoreServices\boot.efi
Boot0081* Mac OS X  ...\System\Library\CoreServices\boot.efi
Boot0082*           ...\System\Library\CoreServices\boot.efi
```

No `ubuntu`, no `GRUB`, no `Linux`. The active entry (`0080`) points at an
Apple-shaped `boot.efi` path on the ESP — the usual place **OpenCore** installs
itself. OpenCore then presents its own picker and boots the kernel.

### What this means in practice

- **`/etc/default/grub` and `update-grub` do nothing on this machine.** Editing
  `GRUB_DEFAULT`, `GRUB_TIMEOUT` or `GRUB_CMDLINE_LINUX_DEFAULT` will not change how it
  boots. Any earlier note claiming otherwise was wrong.
- **Kernel selection is OpenCore's**, not GRUB's. That is why the sequence is
  "select EFI, then EFI again" — the firmware picker, then OpenCore's picker.
- **Kernel parameters must be added in OpenCore's config**, not on the Linux side.
  Prefer fixes that do not need a kernel parameter at all — see [input.md](input.md)
  for one done that way deliberately.

### The bare `grub>` prompt

Pressing `Shift`/`Esc` during boot has produced a bare GRUB command line. GRUB *is*
installed on disk, it is simply not the configured boot path. Chainloading it lands in
a GRUB that never found its own `grub.cfg`, hence a prompt rather than a menu. It is a
side road, not the main one — recovering usually means going back to the OpenCore
picker rather than trying to drive that prompt.

If you do need to boot from it by hand:

```
grub> ls
grub> ls (hd0,gpt3)/boot                     # confirm the real filenames first
grub> set root=(hd0,gpt3)
grub> linux /boot/vmlinuz-7.0.0-30-generic root=UUID=7e20499d-3977-4253-9dfc-590530d5b1fe ro
grub> initrd /boot/initrd.img-7.0.0-30-generic
grub> boot
```

**TODO** (needs sudo): read the ESP and record what is actually there —
`sudo ls -R /boot/efi/EFI/` — then document OpenCore's entry list, its `config.plist`
location, and which entry leads to Linux.

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
