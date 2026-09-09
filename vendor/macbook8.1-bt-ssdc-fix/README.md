# macbook-bt-ssdc-fix

Enable Broadcom Bluetooth on the **Apple MacBook8,1** (and similar Macs) under Linux,
where Bluetooth silently fails to appear despite a working driver.

If your Mac has WiFi but **no `hci0`, no Bluetooth adapter, and `rfkill` only lists
WiFi**, this is almost certainly your problem.

---

## TL;DR

```bash
sudo ./fix-bt-ssdc.sh --dry-run   # build + validate, change nothing
sudo ./fix-bt-ssdc.sh             # install the override
sudo reboot
sudo ./fix-bt-ssdc.sh --diagnose  # confirm it took effect
```

After reboot you should have a working `hci0` Bluetooth adapter.

---

## The problem

On the MacBook8,1 the Bluetooth Broadcom chip is wired to a UART
(`\_SB.PCI0.URT0`, PCI `00:15.5`). In ACPI firmware, **two** serial-device
("serdev") slaves are declared on that *same* UART:

| ACPI device | Identifier            | What it is                                   |
| ----------- | --------------------- | -------------------------------------------- |
| `URT0.BLTH` | `_HID BCM2E7C`        | The real Broadcom Bluetooth (`hci_uart_bcm`) |
| `URT0.SSDC` | `_CID apple-uart-ssdc`| An SSD debug port muxed onto the same UART    |

The Linux **serdev subsystem permits only one slave per UART.** It binds `SSDC`
first — which appears as `serial0-0` with **no driver attached**, because nothing
in Linux matches `apple-uart-ssdc`. The slot is now consumed, so the real
Bluetooth device (`BLTH` / `BCM2E7C`) **never gets a serdev device**, the
`hci_uart_bcm` driver never binds, and no `hci0` is created.

This is a fundamental serdev limitation. It **cannot** be fixed in the Bluetooth
driver source — the conflict happens before the driver is ever consulted.

## The fix

Disable the `SSDC` debug port in ACPI so serdev is free to bind the real
Bluetooth. The script does this with a **DSDT override**, packaged as an early
initrd and wired into GRUB so it survives kernel updates.

What the script does, step by step:

1. **Dump** the live `DSDT` and `SSDT*` tables from `/sys/firmware/acpi/tables/`.
2. **Decompile** the DSDT with `iasl`, supplying the SSDTs as externals so it
   resolves cleanly.
3. **Patch** the `Device (SSDC)` block: rewrite its `_STA` method to
   `Return (Zero)` so the OS sees SSDC as *not present*. (`_DSM` and other
   methods are left untouched.)
4. **Bump the OEM Revision** in the `DefinitionBlock` (see note below — this is
   essential).
5. **Recompile** to `dsdt.aml`.
6. **Package** the AML at `kernel/firmware/acpi/dsdt.aml` inside a `cpio` archive
   → `/boot/acpi_override_ssdc.img`.
7. **Wire it into GRUB** via `GRUB_EARLY_INITRD_LINUX_CUSTOM` and run
   `update-grub`.

At boot, the kernel's ACPI table-upgrade mechanism
(`CONFIG_ACPI_TABLE_UPGRADE=y`, on by default in mainstream distros) loads our
DSDT from the early initrd and replaces the firmware one. SSDC reports
"not present", serdev skips it, `hci_uart_bcm` binds to `BCM2E7C`, and `hci0`
appears.

### Why the OEM Revision bump matters

An initrd ACPI table override is **not** applied unconditionally. The kernel
matches the override against the firmware table on **signature + OEM ID + OEM
Table ID**, and only **upgrades** the platform table if the override carries a
**strictly newer OEM Revision**. With an *equal* revision the kernel silently
keeps the firmware DSDT — no error, no taint, no effect.

The original attempt failed for exactly this reason. The script now increments
the OEM Revision by 1 before compiling, which is what makes the override
actually take effect.

Reference: <https://docs.kernel.org/admin-guide/acpi/initrd_table_override.html>

---

## Requirements

- A **MacBook8,1** (or another Mac exhibiting the SSDC/BLTH UART conflict).
- Linux with `CONFIG_ACPI_TABLE_UPGRADE=y` (default on Ubuntu, Fedora, Arch, …).
- `acpica-tools` (provides `iasl`) and `cpio` — the script auto-installs
  `acpica-tools` on apt/dnf/pacman systems.
- **Secure Boot / kernel lockdown disabled.** Lockdown blocks initrd ACPI
  overrides; the `--diagnose` mode checks this for you.
- A working Broadcom Bluetooth driver (`hci_uart` / `hci_uart_bcm`). On the
  MacBook8,1 this typically comes from the
  [mikeroyal/macbook12-bluetooth-driver](https://github.com/mikeroyal/macbook12-bluetooth-driver)
  DKMS module. **This fix is complementary** — it makes serdev able to bind that
  driver; it does not replace it.

## Usage

```bash
# Validate without changing anything (dumps, patches, recompiles in a temp dir)
sudo ./fix-bt-ssdc.sh --dry-run

# Install the override and wire it into GRUB
sudo ./fix-bt-ssdc.sh

# Reboot to apply
sudo reboot

# After reboot: confirm the override took effect and BT is present
sudo ./fix-bt-ssdc.sh --diagnose

# Revert everything (removes the image + GRUB entry, regenerates GRUB)
sudo ./fix-bt-ssdc.sh --uninstall
```

### Verifying success

After reboot, you should see:

```bash
ls /sys/class/bluetooth          # contains hci0
rfkill list                      # lists a Bluetooth device, not just WiFi
cat /sys/bus/serial/devices/serial0-0/firmware_node/path
                                 # ...URT0.BLTH  (not ...URT0.SSDC)
```

`sudo ./fix-bt-ssdc.sh --diagnose` checks the five things that can block an
initrd DSDT override:

1. Secure Boot / kernel lockdown state.
2. **Kernel taint bit 8** (value `256` = "ACPI table overridden") — the
   definitive "it worked" signal.
3. The early-ACPI `dmesg` trail (`found in initrd` / `Table Upgrade`).
4. The live DSDT's `SSDC._STA` — should now be `Zero`, not `0x0F`.
5. Bluetooth adapter presence.

## Safety and reversibility

- **`--dry-run`** changes nothing on disk — it only exercises the dump/patch/
  compile path in a temp directory.
- Backups of the patched DSL/AML and `/etc/default/grub` are saved to
  `/var/lib/macbook-bt-ssdc`, plus a timestamped `/etc/default/grub.bak.*` on
  each install.
- **`--uninstall`** removes the override image and the GRUB entry and
  regenerates the GRUB config, reverting to the stock firmware DSDT.
- The override only adds a table to the early initrd; if anything goes wrong you
  can also remove `/boot/acpi_override_ssdc.img` and the
  `GRUB_EARLY_INITRD_LINUX_CUSTOM` line manually, then `update-grub`.

## How it persists across kernel updates

The override lives in `/boot` and is referenced by
`GRUB_EARLY_INITRD_LINUX_CUSTOM`, which GRUB prepends to the initrd for **every**
kernel entry it generates. Installing a new kernel re-runs `update-grub`, which
re-applies the early initrd automatically — no reinstall needed.

## Troubleshooting

| Symptom                                   | Likely cause / action                                              |
| ----------------------------------------- | ------------------------------------------------------------------ |
| Still no `hci0` after reboot              | Run `--diagnose`. Check taint bit 8 and the live `SSDC._STA`.       |
| Taint bit 8 clear, no `Table Upgrade` log | OEM Revision not newer, or Secure Boot/lockdown on. See above.      |
| `serial0-0` still points at `SSDC`        | Override didn't apply — re-check GRUB wiring and reboot.            |
| `No 'Device (SSDC)' found`                | Your Mac doesn't have this conflict; BT failure is something else. |

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- The [mikeroyal/macbook12-bluetooth-driver](https://github.com/mikeroyal/macbook12-bluetooth-driver)
  project for the Broadcom `hci_uart` DKMS driver this fix complements.
- The Linux kernel ACPI table-override documentation.
