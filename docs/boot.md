# Boot, firmware and kernels

> **INCOMPLETE.** The OpenCore side of this is not yet documented — the details are
> still with the person who set it up. Everything below is what the running system
> reports plus observed symptoms. Sections marked **TODO** are the gaps.

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
| Firmware | EFI (`/sys/firmware/efi` present) |
| Apple BIOS version | `481.0.0.0.0`, dated 2023-01-12 |
| Secure Boot | **Not supported on this machine** — unsigned kernel modules load freely |

## Boot chain

```
Apple EFI firmware  ->  [OpenCore]  ->  GRUB  ->  kernel
```

**TODO:** where OpenCore lives, how it is configured, which entries it presents, and
which one leads to GRUB rather than macOS.

---

## GRUB configuration

```
GRUB_DEFAULT=0                 # first entry = newest kernel = 7.0 currently
GRUB_TIMEOUT_STYLE=menu
GRUB_TIMEOUT=15
GRUB_RECORDFAIL_TIMEOUT=15
GRUB_CMDLINE_LINUX_DEFAULT=""  # no quiet, no splash - boot messages are visible
```

Note that the menu is **already** configured to display for 15 seconds. You should not
need to hold anything to get it.

### Observed boot problems

Recorded so they are recognisable next time; causes not yet confirmed.

- **Black screen after selecting EFI, then EFI again.** Reproducible during the
  attempts to get back into Linux.
- **`Shift`+`Esc` produced a bare GRUB command line instead of the menu.** Given
  `GRUB_TIMEOUT_STYLE=menu` is already set, a bare `grub>` prompt means GRUB started
  but **never loaded its `grub.cfg`** — it did not simply "skip" the menu. That
  usually points at the boot entry launching a GRUB EFI binary that cannot find its
  own `$prefix`, rather than at a GRUB configuration problem.

**TODO:** confirm against the OpenCore entry list which EFI binary each menu item
actually launches.

### Recovering from a bare `grub>` prompt

Boot by hand from the prompt:

```
grub> ls                                     # find the partitions
grub> ls (hd0,gpt3)/boot                     # confirm the kernel names first
grub> set root=(hd0,gpt3)
grub> linux /boot/vmlinuz-7.0.0-30-generic root=UUID=7e20499d-3977-4253-9dfc-590530d5b1fe ro
grub> initrd /boot/initrd.img-7.0.0-30-generic
grub> boot
```

Substitute the 6.14 filenames to boot the older kernel. Verify the exact names with
the `ls` line — do not assume them.

Once booted, regenerate the config properly:

```bash
sudo update-grub
```

---

## Kernels

| Kernel | Status |
|---|---|
| `7.0.0-30-generic` | **Current and default.** Ubuntu HWE (`linux-hwe-7.0`). Everything works. |
| `6.14.0-37-generic` | **Keyboard and trackpad do not work.** Effectively unusable. |

7.0 arrived through a routine Update Manager run and became the default because
`GRUB_DEFAULT=0` selects the newest entry. Selecting 6.14 requires
**Advanced options for Linux Mint** in the GRUB menu.

### 6.14 has no working input

Neither the built-in keyboard nor the trackpad respond under 6.14. **This blocks the
audio work** — the one remaining cheap test for the speaker driver needs to run on
6.14, and the machine cannot be driven there. See [audio.md](audio.md).

**TODO:** diagnose. The 12-inch MacBook uses SPI-attached input
(`applespi` / `spi_pxa2xx_pci`), not USB or I2C, and that driver historically needed
specific DSDT/ACPI conditions. Under 7.0 the input devices work, so comparing the
loaded input modules and `dmesg` between the two kernels is the obvious first step.
Since 6.14 cannot be typed on, capture the evidence by booting it with a **USB
keyboard** attached, or read its logs afterwards from 7.0 with
`journalctl --boot=-1`.

### Do not let DKMS build for 7.0

The out-of-tree audio driver **panics at probe on 7.0** and takes the whole analog
card down with it. Its `dkms.conf` sets `AUTOINSTALL="yes"`, so it will rebuild itself
for every newly installed kernel. If it is ever installed for 6.14, immediately check
and remove any 7.0 build:

```bash
dkms status
sudo dkms remove -m macbook12-audio-driver -v 0.1 -k 7.0.0-30-generic
```

---

## Rollback safety

Both kernels remain installed and selectable, so a bad kernel is never a dead end —
pick the other one from the GRUB menu. `timeshift` is installed; take a snapshot
before anything that touches kernels or modules:

```bash
sudo timeshift --create --comments "before <change>"
```
