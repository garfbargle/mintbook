# Bluetooth — BCM4350 UART on the 12-inch MacBook

**Status: WORKING on 7.0.** Confirmed 2026-09-01 after reboot with the DSDT
override prepended to `initrd.img-7.0.0-30-generic`. `serial0-0` is
`\_SB_.PCI0.URT0.BLTH`, driver `hci_uart_bcm`. `/sys/class/bluetooth/hci0`
exists. Chip is **BCM4350C0** UART, ROM firmware `003.001.134` build 1532.
No DKMS, no `.hcd`.

This page is the radio: why there was no adapter and what makes one exist.
**The desktop half — the bar icon and the popup behind it — is in
[desktop.md](desktop.md#bluetooth-menu-binbt-menu).** Two installers, and they
are easy to confuse:

| | what it does | root? |
|---|---|---|
| [`bin/bt-install`](../bin/bt-install) | the DSDT override that makes `hci0` exist | **yes** |
| [`bin/bt-panel-install`](../bin/bt-panel-install) | the bar icon and [`bin/bt-menu`](../bin/bt-menu) | no |

`bin/bt-diag` and `bin/doctor` cover both: the DSDT checks are in doctor's
Bluetooth section, the icon and menu checks run only once
`~/.config/mintbook/bluetooth.conf` exists.

---

## Why there was no adapter

Before the override:

```
dmesg:  serial serial0-0: failure adding ACPI serdev device. status -EBUSY
serial0-0 path:     \_SB_.PCI0.URT0.SSDC
serial0-0 modalias: acpi:APPLE-UART-SSDC:
BCM2E7C:00          \_SB_.PCI0.URT0.BLTH  hid=BCM2E7C  status=15
/sys/class/bluetooth/   empty
```

The Broadcom chip is wired to UART0 (`\_SB.PCI0.URT0`, PCI `00:15.5`,
`8250_lpss`). ACPI declares **two** serdev slaves on that same UART:

| ACPI device | Identifier | What it is |
|---|---|---|
| `URT0.BLTH` | `_HID BCM2E7C` | Real Broadcom Bluetooth (`hci_uart_bcm`) |
| `URT0.SSDC` | `_CID apple-uart-ssdc` | SSD debug port muxed onto the same lines |

Linux serdev allows **one** slave per UART. It binds `SSDC` first. Nothing in
Linux matches `apple-uart-ssdc`, so `serial0-0` sat there with no driver.
`BLTH` stayed an ACPI device (`status=15`) and never got a serdev node, so
`hci_uart_bcm` never probed and no `hci0` was created.

This happens **before** the Bluetooth driver is consulted. It cannot be fixed
in `hci_bcm.c`.

---

## What was ruled out

| Suspect | Verdict |
|---|---|
| Missing Broadcom `.hcd` firmware | **Not the blocker, and not wanted.** After bind the driver logs `BCM: firmware Patch file not found` for `brcm/BCM.hcd`. That is expected. The chip uses ROM firmware `003.001.134`. Do **not** drop a random `BCM.hcd` in `/lib/firmware/brcm/` — C5 firmware on a C0 chip has bricked HCI on sibling Macs. |
| `macbook12-bluetooth-driver` DKMS | **Not needed on 7.0.** In-tree `hci_uart` already has `acpi*:BCM2E7C:*` and the Apple `BTLP` / `BTPU` / `BTPD` methods. Confirmed: it bound `hci_uart_bcm` with no extra module. |
| `bluetooth.service` / blueman / bluez | Already installed. Not the problem. |
| Wi-Fi `brcmfmac` firmware | Separate. Wi-Fi was already working (`BCM4350/5`). |
| `GRUB_EARLY_INITRD_LINUX_CUSTOM` | **Does not apply here.** OpenLinuxBoot loads a single `initrd=\boot\initrd.img-<ver>`. It does not read that GRUB variable. In GRUB2/blscfg mode `$early_initrd` is unsupported and would abort the boot. |
| Kernel taint bit 8 | **Unreliable on 7.0.** The table *did* upgrade (`ACPI: Table Upgrade: override [DSDT-APPLE - MacBook]`) but taint stayed `12288` (OOT + unsigned modules only). Treat `Table Upgrade` in dmesg and `serial0-0` = `URT0.BLTH` as the success signals. |

---

## The fix

Disable `SSDC` in ACPI so serdev is free to bind `BLTH`. Dump the live DSDT,
rewrite `Device (SSDC)` `_STA` to `Return (Zero)`, **bump the OEM Revision by
1** (`0x00080001` → `0x00080002`), recompile, and package the AML as
`kernel/firmware/acpi/dsdt.aml` inside an uncompressed cpio.

The kernel (`CONFIG_ACPI_TABLE_UPGRADE=y`, lockdown off) only **replaces** the
firmware DSDT when the override matches signature + OEM ID + OEM Table ID and
carries a **strictly newer** OEM Revision. An equal revision is silently
ignored — no error, no effect.

This machine boots:

```
OpenCore → OpenLinuxBoot → EFISTUB
  initrd=\boot\initrd.img-7.0.0-30-generic
```

So the override is **prepended to that initrd file**. A post-update hook
re-prepends after every `update-initramfs` for kernels that are not 6.14.
`update-grub` is not run. 6.14's initrd is left stock on purpose.

---

## What this session did

1. Confirmed the live conflict: `serial0-0` = `URT0.SSDC`, `BCM2E7C` present
   but unbound, dmesg `-EBUSY`, no `/sys/class/bluetooth/`.
2. Confirmed `CONFIG_ACPI_TABLE_UPGRADE=y`, lockdown `[none]`, in-tree
   `hci_uart` already matches `BCM2E7C`.
3. Adapted [thomas-shirley/macbook8.1-bt-ssdc-fix](https://github.com/thomas-shirley/macbook8.1-bt-ssdc-fix)
   to this boot path: same DSDT patch, initrd prepend instead of GRUB.
4. `apt-get update` cannot be used here — the Cursor apt repo is unsigned and
   fails the whole update. `bt-install` installs `acpica-tools` from the
   existing Ubuntu cache.
5. Timeshift `--create` hung at rsync 0% and was cancelled. 6.14 remains the
   ACPI fallback.
6. After reboot into 7.0 (2026-09-01 21:02):

```
ACPI: DSDT ACPI table found in initrd [kernel/firmware/acpi/dsdt.aml]
ACPI: Table Upgrade: override [DSDT-APPLE - MacBook]
serial0-0 path:     \_SB_.PCI0.URT0.BLTH
serial0-0 driver:   hci_uart_bcm
APPLE-UART-SSDC:00  status=0
BCM2E7C:00          status=15
/sys/class/bluetooth/hci0
Bluetooth: hci0: BCM4350C0 UART 37.4 MHz Gamay USI UHE
Bluetooth: hci0: BCM (003.001.134) build 1532
```

`hci0: Failed to set baudrate` / `failed to write update baudrate (-16)` is
the known Apple UART behaviour (speed is fixed). The probe continues and
identifies the chip. Harmless.

`unknown advertising packet type: 0x10` (and similar) is BLE advertising the
stack does not parse. Noisy, not a bind failure.

---

## Install

The script builds the override, installs the hook, and regenerates the
**running** kernel's initrd. It does **not** run `update-grub` and it will
refuse to patch 6.14. Timeshift is optional on this box (rsync hung at 0%).

```
sudo /home/cobo/mintbook/bin/bt-install --dry-run
sudo /home/cobo/mintbook/bin/bt-install
sudo reboot
```

After reboot, stay on 7.0:

```
cat /proc/cmdline          # still 7.0, still intel_iommu=off
bin/bt-diag
```

Success looks like:

```
dmesg: DSDT ACPI table found in initrd / Table Upgrade
serial0-0 path: \_SB_.PCI0.URT0.BLTH
serial0-0 driver: hci_uart_bcm
ls /sys/class/bluetooth    # hci0
```

---

## Rollback

```
sudo /home/cobo/mintbook/bin/bt-install --uninstall
sudo reboot
```

That removes `/boot/acpi_override_ssdc.img` and the post-update hook, then
regenerates the running kernel's initrd without the prepend. If 7.0 will not
boot, pick **6.14** in OpenCanopy (untouched initrd) and run `--uninstall`
from there.

Manual:

```
sudo rm -f /boot/acpi_override_ssdc.img \
           /etc/initramfs/post-update.d/zz-acpi-ssdc-override
sudo update-initramfs -u -k 7.0.0-30-generic
```

Backups of the patched DSL/AML live in `/var/lib/macbook-bt-ssdc`.

---

## If `hci0` disappears after a kernel update

The hook at `/etc/initramfs/post-update.d/zz-acpi-ssdc-override` must still
exist and `/boot/acpi_override_ssdc.img` must still exist. `update-initramfs`
rebuilds a stock image, then the hook prepends the override. If either file
is gone, `serial0-0` will go back to `URT0.SSDC`. Re-run `bin/bt-install`.

---

## Source used

| | |
|---|---|
| Problem + DSDT patch | `/home/cobo/src/macbook8.1-bt-ssdc-fix` |
| Upstream | [thomas-shirley/macbook8.1-bt-ssdc-fix](https://github.com/thomas-shirley/macbook8.1-bt-ssdc-fix) |
| In-tree driver | `hci_uart` / `hci_uart_bcm` on `7.0.0-30-generic` |
| Hook | [`config/initramfs/zz-acpi-ssdc-override`](../config/initramfs/zz-acpi-ssdc-override) |
