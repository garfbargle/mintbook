#!/usr/bin/env bash
#
# fix-bt-ssdc.sh — Enable Broadcom Bluetooth on the MacBook8,1 (and similar)
#
# Problem: the Bluetooth UART (\_SB.PCI0.URT0) exposes TWO serdev slaves:
#   - URT0.BLTH (HID BCM2E7C)        -> the real Broadcom BT (hci_uart_bcm)
#   - URT0.SSDC (HID APPLE-UART-SSDC)-> an SSD debug port muxed on the same UART
# Linux serdev allows only ONE slave per UART, and it grabs SSDC first, so the
# real Bluetooth never gets a serdev device -> no hci0.
#
# Fix: override the DSDT so SSDC reports _STA = 0 (not present). serdev then
# binds hci_uart_bcm to BCM2E7C and hci0 appears. The override DSDT is packaged
# as an early-initrd cpio and wired into GRUB via GRUB_EARLY_INITRD_LINUX_CUSTOM,
# so it persists across kernel updates.
#
# Usage:
#   sudo ./fix-bt-ssdc.sh            # build + install the override
#   sudo ./fix-bt-ssdc.sh --dry-run  # build + validate only; touch nothing
#   sudo ./fix-bt-ssdc.sh --diagnose # check whether the override took effect
#   sudo ./fix-bt-ssdc.sh --uninstall
#
# Reversible: keeps backups and an --uninstall path. Reboot required to apply.

set -euo pipefail

OVERRIDE_NAME="acpi_override_ssdc.img"
OVERRIDE_PATH="/boot/${OVERRIDE_NAME}"
GRUB_DEFAULT="/etc/default/grub"
BACKUP_DIR="/var/lib/macbook-bt-ssdc"
WORK=""

DRYRUN=0

log()  { printf '\033[1;34m[*]\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m[+]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

cleanup() { [ -n "$WORK" ] && [ -d "$WORK" ] && rm -rf "$WORK"; }
trap cleanup EXIT

require_root() {
  [ "$(id -u)" -eq 0 ] || die "Run as root: sudo $0 $*"
}

# --------------------------------------------------------------------------
# Uninstall: drop the GRUB early-initrd entry, remove the image, regenerate.
# --------------------------------------------------------------------------
uninstall() {
  require_root "$@"
  log "Removing GRUB early-initrd entry for ${OVERRIDE_NAME}..."
  if grep -q "^GRUB_EARLY_INITRD_LINUX_CUSTOM=.*${OVERRIDE_NAME}" "$GRUB_DEFAULT" 2>/dev/null; then
    # Strip just our image from the (possibly multi-value) variable.
    cp -a "$GRUB_DEFAULT" "${GRUB_DEFAULT}.bak.$(date +%s)"
    sed -i -E "s/(GRUB_EARLY_INITRD_LINUX_CUSTOM=\")([^\"]*)(\")/\1\2\3/" "$GRUB_DEFAULT"
    # Remove the token and tidy whitespace; drop the line entirely if now empty.
    sed -i -E "/^GRUB_EARLY_INITRD_LINUX_CUSTOM=/{s/${OVERRIDE_NAME}//; s/\"[[:space:]]+/\"/; s/[[:space:]]+\"/\"/; s/[[:space:]]{2,}/ /g}" "$GRUB_DEFAULT"
    sed -i -E "/^GRUB_EARLY_INITRD_LINUX_CUSTOM=\"[[:space:]]*\"$/d" "$GRUB_DEFAULT"
  fi
  rm -f "$OVERRIDE_PATH"
  ok "Removed ${OVERRIDE_PATH} and GRUB entry."
  update_grub
  ok "Uninstalled. Reboot to revert to the stock DSDT."
  exit 0
}

# --------------------------------------------------------------------------
# Preconditions
# --------------------------------------------------------------------------
check_machine() {
  local model=""
  [ -r /sys/class/dmi/id/product_name ] && model="$(cat /sys/class/dmi/id/product_name)"
  log "Detected model: ${model:-unknown}"
  case "$model" in
    MacBook8,1) ok "Supported model." ;;
    MacBook*)   warn "Untested Mac model ($model). Continuing, but verify SSDC exists." ;;
    *)          warn "Non-MacBook DMI ($model). This fix is specific to the SSDC/BLTH UART conflict." ;;
  esac
}

ensure_tools() {
  if ! command -v iasl >/dev/null 2>&1; then
    log "Installing acpica-tools (iasl)..."
    if command -v apt-get >/dev/null 2>&1; then
      apt-get update -qq && apt-get install -y acpica-tools
    elif command -v dnf >/dev/null 2>&1; then
      dnf install -y acpica-tools
    elif command -v pacman >/dev/null 2>&1; then
      pacman -Sy --noconfirm acpica
    else
      die "Could not auto-install iasl. Install 'acpica-tools' (or 'acpica') and re-run."
    fi
  fi
  command -v cpio >/dev/null 2>&1 || die "Missing 'cpio'. Install it and re-run."
  ok "Tooling present: iasl, cpio."
}

# --------------------------------------------------------------------------
# Dump DSDT + SSDTs and decompile (SSDTs as externals so DSDT compiles clean).
# --------------------------------------------------------------------------
dump_and_decompile() {
  WORK="$(mktemp -d)"
  log "Dumping ACPI tables to $WORK ..."
  [ -r /sys/firmware/acpi/tables/DSDT ] || die "Cannot read DSDT (need root / mounted sysfs)."
  cp /sys/firmware/acpi/tables/DSDT "$WORK/dsdt.dat"

  local i=0
  local -a ssdts=()
  for t in /sys/firmware/acpi/tables/SSDT*; do
    [ -e "$t" ] || continue
    cp "$t" "$WORK/ssdt_${i}.dat"
    ssdts+=("ssdt_${i}.dat")   # iasl -e wants space-separated names, not comma-joined
    i=$((i+1))
  done
  if [ "${#ssdts[@]}" -gt 0 ]; then
    log "Decompiling DSDT with ${#ssdts[@]} SSDT(s) as externals..."
    ( cd "$WORK" && iasl -e "${ssdts[@]}" -d dsdt.dat >/dev/null 2>&1 ) || true
  else
    log "No SSDTs found; decompiling DSDT alone..."
    ( cd "$WORK" && iasl -d dsdt.dat >/dev/null 2>&1 ) || true
  fi
  [ -f "$WORK/dsdt.dsl" ] || die "Decompilation failed (no dsdt.dsl produced)."
  ok "Decompiled to dsdt.dsl"
}

# --------------------------------------------------------------------------
# Verify SSDC is present, is the right device, and has no existing _STA.
# Then inject _STA { Return (Zero) } and bump the OEM revision.
# --------------------------------------------------------------------------
patch_dsdt() {
  local dsl="$WORK/dsdt.dsl"

  grep -q 'Device (SSDC)' "$dsl" \
    || die "No 'Device (SSDC)' found in DSDT. Nothing to patch (BT may fail for another reason)."

  # Extract the SSDC device block via brace matching, for inspection.
  awk '
    /Device \(SSDC\)/ { found=1 }
    found {
      print
      n = gsub(/\{/, "{"); o = gsub(/\}/, "}")
      depth += n - o
      if (n > 0) started = 1
      if (started && depth == 0) exit
    }
  ' "$dsl" > "$WORK/ssdc.block"

  # The Apple BT-debug device identifies via _CID/_HID "apple-uart-ssdc" (case varies).
  grep -iq 'apple-uart-ssdc' "$WORK/ssdc.block" \
    || warn "SSDC block does not mention apple-uart-ssdc — patching anyway, please verify."

  if grep -qE 'Method \(_STA|Name \(_STA' "$WORK/ssdc.block"; then
    # SSDC already reports _STA (typically Return (0x0F) = present). Rewrite ONLY the
    # _STA method's return to Zero, leaving _DSM and other returns untouched.
    log "SSDC has an existing _STA; rewriting its return to Zero..."
    awk '
      !done && /Device \(SSDC\)/ { in_ssdc = 1 }
      in_ssdc && !done && /Method \(_STA|Name \(_STA/ { in_sta = 1 }
      {
        if (in_sta && !done && sta_open == 1 && $0 ~ /Return \(/) {
          sub(/Return \([^)]*\)/, "Return (Zero)  /* disabled by fix-bt-ssdc.sh */")
          done = 1
        }
        print
        n = gsub(/\{/, "{"); o = gsub(/\}/, "}")
        if (in_sta) { sta_depth += n - o; if (n > 0) sta_open = 1; if (sta_open && sta_depth == 0) in_sta = 0 }
        if (in_ssdc) { ssdc_depth += n - o; if (n > 0) ssdc_seen = 1; if (ssdc_seen && ssdc_depth == 0) in_ssdc = 0 }
      }
    ' "$dsl" > "$WORK/dsdt.patched.dsl"
  else
    # No _STA present: inject one returning Zero right after the device opening brace.
    log "Injecting _STA -> Zero into Device (SSDC)..."
    awk '
      !injected && /Device \(SSDC\)/ { insscd = 1 }
      { print }
      insscd && !injected && /\{/ {
        print "                Method (_STA, 0, NotSerialized)"
        print "                {"
        print "                    Return (Zero)  /* disabled by fix-bt-ssdc.sh */"
        print "                }"
        injected = 1; insscd = 0
      }
    ' "$dsl" > "$WORK/dsdt.patched.dsl"
  fi

  grep -q 'disabled by fix-bt-ssdc.sh' "$WORK/dsdt.patched.dsl" \
    || die "Patch failed (marker not found)."

  # Bump the OEM Revision. The initrd table-upgrade mechanism only REPLACES the
  # platform DSDT when the override matches on signature + OEM ID + OEM Table ID
  # AND carries a *more recent* OEM Revision; with an equal revision the kernel
  # merely appends our table and keeps the firmware DSDT (no override, no taint).
  local oldrev newrev
  oldrev="$(grep -m1 'DefinitionBlock' "$WORK/dsdt.patched.dsl" \
            | grep -oE '0x[0-9A-Fa-f]+[[:space:]]*\)' | grep -oE '0x[0-9A-Fa-f]+')"
  [ -n "$oldrev" ] || die "Could not find OEM Revision in DefinitionBlock to bump."
  newrev="$(printf '0x%08X' "$(( oldrev + 1 ))")"
  sed -i -E "s/(DefinitionBlock[^)]*,[[:space:]]*)0x[0-9A-Fa-f]+([[:space:]]*\))/\1${newrev}\2/" \
    "$WORK/dsdt.patched.dsl"
  grep -q "${newrev})" "$WORK/dsdt.patched.dsl" \
    || warn "OEM Revision bump may not have applied (wanted ${newrev}); verify DefinitionBlock."
  log "OEM Revision bumped ${oldrev} -> ${newrev} so the kernel upgrades the DSDT."

  mv "$WORK/dsdt.patched.dsl" "$dsl"
  ok "DSDT patched."
}

compile_dsdt() {
  log "Recompiling patched DSDT..."
  ( cd "$WORK" && iasl dsdt.dsl >/dev/null 2>&1 ) || {
    warn "Clean compile failed; retrying with -f (force) ..."
    ( cd "$WORK" && iasl -f dsdt.dsl >/dev/null 2>&1 ) || true
  }
  [ -f "$WORK/dsdt.aml" ] || die "Compilation failed (no dsdt.aml). See: cd $WORK && iasl dsdt.dsl"
  ok "Compiled dsdt.aml"
}

build_override() {
  log "Building early-initrd ACPI override cpio..."
  local stage="$WORK/cpio/kernel/firmware/acpi"
  mkdir -p "$stage"
  cp "$WORK/dsdt.aml" "$stage/dsdt.aml"
  ( cd "$WORK/cpio" && find kernel | cpio -H newc --create 2>/dev/null > "$WORK/$OVERRIDE_NAME" )
  install -m 0644 "$WORK/$OVERRIDE_NAME" "$OVERRIDE_PATH"
  ok "Installed override image: $OVERRIDE_PATH"
}

save_backups() {
  mkdir -p "$BACKUP_DIR"
  cp "$WORK/dsdt.dsl" "$BACKUP_DIR/dsdt.dsl"
  cp "$WORK/dsdt.aml" "$BACKUP_DIR/dsdt.aml"
  cp -a "$GRUB_DEFAULT" "$BACKUP_DIR/grub.default.bak"
  ok "Backups saved to $BACKUP_DIR"
}

wire_grub() {
  log "Wiring override into GRUB (GRUB_EARLY_INITRD_LINUX_CUSTOM)..."
  cp -a "$GRUB_DEFAULT" "${GRUB_DEFAULT}.bak.$(date +%s)"
  if grep -q '^GRUB_EARLY_INITRD_LINUX_CUSTOM=' "$GRUB_DEFAULT"; then
    if grep -q "^GRUB_EARLY_INITRD_LINUX_CUSTOM=.*${OVERRIDE_NAME}" "$GRUB_DEFAULT"; then
      ok "GRUB already references ${OVERRIDE_NAME}."
    else
      # Append our image to the existing space-separated list.
      sed -i -E "s/(^GRUB_EARLY_INITRD_LINUX_CUSTOM=\")([^\"]*)(\")/\1\2 ${OVERRIDE_NAME}\3/" "$GRUB_DEFAULT"
      sed -i -E "s/(^GRUB_EARLY_INITRD_LINUX_CUSTOM=\") +/\1/" "$GRUB_DEFAULT"  # tidy leading space
      ok "Appended ${OVERRIDE_NAME} to GRUB_EARLY_INITRD_LINUX_CUSTOM."
    fi
  else
    printf 'GRUB_EARLY_INITRD_LINUX_CUSTOM="%s"\n' "$OVERRIDE_NAME" >> "$GRUB_DEFAULT"
    ok "Added GRUB_EARLY_INITRD_LINUX_CUSTOM=\"${OVERRIDE_NAME}\"."
  fi
}

update_grub() {
  log "Regenerating GRUB config..."
  if command -v update-grub >/dev/null 2>&1; then
    update-grub
  elif command -v grub-mkconfig >/dev/null 2>&1; then
    grub-mkconfig -o /boot/grub/grub.cfg
  elif command -v grub2-mkconfig >/dev/null 2>&1; then
    grub2-mkconfig -o /boot/grub2/grub.cfg
  else
    die "No grub config generator found (update-grub / grub-mkconfig)."
  fi
  ok "GRUB config updated."
}

# --------------------------------------------------------------------------
# Diagnose: did the override actually take effect? Use after a reboot when BT
# still doesn't show up. Checks the four things that block an initrd DSDT
# override: lockdown/Secure Boot, the taint bit, the early-ACPI dmesg trail,
# and whether the live DSDT's SSDC._STA is now Zero.
# --------------------------------------------------------------------------
diagnose() {
  echo "=== 1. Secure Boot / lockdown (lockdown blocks initrd ACPI overrides) ==="
  if command -v mokutil >/dev/null 2>&1; then
    mokutil --sb-state 2>&1
  else
    warn "mokutil not installed; reading efivars:"
    od -An -t u1 /sys/firmware/efi/efivars/SecureBoot-* 2>/dev/null | tail -c 4 \
      || echo "no SecureBoot efivar"
  fi
  echo "Kernel lockdown: $(cat /sys/kernel/security/lockdown 2>/dev/null || echo 'n/a')"

  echo
  echo "=== 2. Kernel taint bit 8 (256 = ACPI table overridden) ==="
  local t; t="$(cat /proc/sys/kernel/tainted 2>/dev/null || echo 0)"
  echo "tainted = $t"
  if (( (t & 256) != 0 )); then
    ok "ACPI table override DID take effect (bit 8 set)."
  else
    warn "ACPI table override did NOT take effect (bit 8 clear)."
  fi

  echo
  echo "=== 3. Early-ACPI dmesg (found-in-initrd / Table Upgrade / errors) ==="
  dmesg 2>/dev/null | grep -iE \
    'found in initrd|table upgrade|override|tainting|ACPI Error|ACPI BIOS Error|AE_|ignoring.*table' \
    | head -40 || echo "(none — run as root if dmesg is restricted)"

  echo
  echo "=== 4. Live DSDT: is SSDC._STA now Zero (applied) or 0x0F (not applied)? ==="
  if command -v iasl >/dev/null 2>&1 && [ -r /sys/firmware/acpi/tables/DSDT ]; then
    local tmp; tmp="$(mktemp -d)"
    cp /sys/firmware/acpi/tables/DSDT "$tmp/_live.dat"
    ( cd "$tmp" && iasl -d _live.dat >/dev/null 2>&1 ) || true
    awk '
      /Device \(SSDC\)/ { f=1 }
      f {
        print "    " $0
        n = gsub(/\{/, "{"); o = gsub(/\}/, "}")
        d += n - o
        if (n > 0) s = 1
        if (s && d == 0) exit
      }
    ' "$tmp/_live.dsl" 2>/dev/null || echo "(could not decompile live DSDT)"
    rm -rf "$tmp"
  else
    warn "Need iasl + readable DSDT (run as root) to inspect the live SSDC block."
  fi

  echo
  echo "=== 5. Bluetooth presence ==="
  ls /sys/class/bluetooth 2>/dev/null | grep -q hci && ok "hci device present." \
    || warn "No hci device under /sys/class/bluetooth."
  command -v rfkill >/dev/null 2>&1 && rfkill list bluetooth 2>/dev/null

  if [ -r "$BACKUP_DIR/dsdt.dsl" ]; then
    echo
    echo "=== 6. Installed patched DSL — clean recompile to surface AML errors ==="
    if command -v iasl >/dev/null 2>&1; then
      local tmp2; tmp2="$(mktemp -d)"
      cp "$BACKUP_DIR/dsdt.dsl" "$tmp2/recheck.dsl"
      ( cd "$tmp2" && iasl recheck.dsl 2>&1 | tail -20 )
      rm -rf "$tmp2"
    fi
  fi
  exit 0
}

main() {
  require_root "$@"
  check_machine
  ensure_tools
  dump_and_decompile
  patch_dsdt
  compile_dsdt
  if [ "$DRYRUN" -eq 1 ]; then
    echo
    ok "Dry run OK: dumped, patched, and recompiled the DSDT successfully."
    ok "Nothing in /boot or GRUB was modified."
    log "Patched SSDC block:"
    awk '
      /Device \(SSDC\)/ { f=1 }
      f {
        print "    " $0
        n = gsub(/\{/, "{"); o = gsub(/\}/, "}")
        depth += n - o
        if (n > 0) started = 1
        if (started && depth == 0) exit
      }
    ' "$WORK/dsdt.dsl"
    log "Re-run without --dry-run to install."
    return 0
  fi
  build_override
  save_backups
  wire_grub
  update_grub
  echo
  ok "Done. Reboot to apply the DSDT override."
  cat <<EOF

After reboot, verify with:
    sudo $0 --diagnose     # confirms the override applied + BT is present
    rfkill list            # should now list a Bluetooth device
    ls /sys/class/bluetooth # should contain hci0

To revert:  sudo $0 --uninstall
EOF
}

case "${1:-}" in
  --uninstall|-u) uninstall "$@" ;;
  --dry-run|-n)   DRYRUN=1; main "$@" ;;
  --diagnose|-d)  diagnose ;;
  -h|--help)      grep '^#' "$0" | sed 's/^# \{0,1\}//' | head -33 ;;
  "")             main "$@" ;;
  *)              die "Unknown argument: $1 (use --dry-run, --diagnose, --uninstall or --help)" ;;
esac
