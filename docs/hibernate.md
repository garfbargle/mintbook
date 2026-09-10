# Hibernation

**Status 2026-09-10: one combination works — `systemctl hibernate` from the
desktop, on AC. Everything else has failed at least once.**

- **Proven:** X + AC, save and restore, Apple SPI keyboard included. See "The
  cycle that worked".
- **Save hangs** when invoked from X **on battery** (2 of 2). It does not hang
  from a text console on battery, so this is an X-plus-battery interaction, not
  either one alone.
- **Restore has succeeded once and failed once.** The failure was from tty2 on
  battery: "restoring image", then a black screen. Whether the kernel hung or
  merely lost the display is **not yet established**.
- The lid is therefore back on plain `suspend`. Overnight unplugged is **not**
  solved: s2idle still costs ~1.8 W, about 11 hours. Plug in overnight, or
  hibernate by hand on AC.

Also worth keeping: `resume=PARTUUID=` is silently ignored (see "The third
trap"), and the first attempt destroyed its own image.

## Why this exists

On 2026-09-09 the machine went to sleep at 54% and was flat by morning.

It was not woken, and it did not run. The journal for that boot stops mid-suspend
and has nothing after it:

```
Sep 09 22:08:39  systemd-logind: Lid closed.
Sep 09 22:08:42  kernel: PM: suspend entry (s2idle)
                 <nothing until the cold boot at 08:21:43>
```

No file under `/var` or `/tmp` changed between 22:09 and 08:00. It stayed
suspended for ten hours and drained ~18 Wh doing it — about **1.8 W**.

That is a regression introduced by [`1e6aae0`](../docs/input.md) on 2026-09-08,
which selected s2idle to keep the built-in keyboard alive across suspend. The
cost was written down at the time as a guess ("It costs more battery during long
sleeps... Several longer cycles are needed to measure the battery tradeoff").
This is that measurement, taken the expensive way.

### The two modes, measured

Drain across every sleep gap in `/var/lib/upower/history-charge-bq20z451-40.dat`,
attributed by the `PM: suspend entry (...)` mode in the journal. The cutover is
`mintbook-s2idle.service` first running at `Sep 08 21:50:04`.

| Date | Mode | Duration | Drain | Average |
|---|---|---|---|---|
| 09-02 22:31 → 09-03 15:41 | deep | 17.2 h | 6.2% | **0.12 W** |
| 09-03 23:24 → 09-04 18:42 | deep | 19.3 h | 4.8% | **0.08 W** |
| 09-06 04:44 → 08:29 | deep | 3.8 h | 0.7% | **0.06 W** |
| 09-06 11:08 → 14:53 | deep | 3.8 h | 1.6% | **0.14 W** |
| 09-09 22:08 → dead | s2idle | ≤10.2 h | 54.6% | **≥1.8 W** |

s2idle costs roughly **20x** what deep S3 cost. A full charge is about ten hours,
which is exactly one night. Before 09-09 the only s2idle sleeps had been 25
seconds long or on AC, so nothing had exercised the case that matters.

Two earlier deaths (09-05 and 09-06) happened on **deep** S3 and are not explained
by this. The 09-06 one went 97.8% → flat in 64 minutes, which is ~31 W and
therefore not consumption at all. Those remain open; they are not this bug.

## The design

Deep S3 is unusable here — it wedges the Apple SPI endpoint and costs a reboot
(47 timeouts, failed rebind, measured 2026-09-08; see [input.md](input.md)).
s2idle is usable but costs 1.8 W. Neither is survivable overnight on its own.

`suspend-then-hibernate` takes the good half of each:

```
lid closes  ->  s2idle          cheap for a short close, input survives
              (30 minutes)
            ->  hibernate       image to disk, machine powers off, 0 W
            ->  resume          a full boot, so applespi probes from cold
```

The last line is the point. Resume from disk is not an ACPI S3 wake; it is a
kernel boot that happens to restore an image. `applespi` re-probes over the same
PIO path that works at every ordinary boot, which is the path S3 skips.

`SuspendState` is deliberately left unset. Writing `mem` already lands on s2idle
because `mintbook-s2idle.service` owns `/sys/power/mem_sleep`, and one authority
for that is better than two.

## The trap: two owners for the lid

`xfce4-power-manager` holds a `handle-lid-switch` inhibitor by default, so logind
reports its own setting while XFCE does the actual suspending:

```
$ loginctl show-session | grep -E 'BlockInhibited|HandleLidSwitch'
BlockInhibited=handle-power-key:handle-suspend-key:handle-hibernate-key:handle-lid-switch
HandleLidSwitch=suspend
```

Setting `HandleLidSwitch=suspend-then-hibernate` alone changes **nothing**. The
xfconf key has to be flipped too, and it is user-level, not root:

```bash
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/logind-handle-lid-switch -s true
```

`handle-lid-switch` should then be absent from `BlockInhibited`. `bin/hibernate-check`
asserts both halves, because either one alone is a silent no-op.

Locking still works: `light-locker` locks on logind's `PrepareForSleep`, not on
XFCE's lid handler, so moving the lid to logind does not lose the lock.

## The second trap: Ubuntu disables hibernation in polkit

With the swap file in place and the resume device set, logind still said:

```
$ busctl call org.freedesktop.login1 /org/freedesktop/login1 \
      org.freedesktop.login1.Manager CanHibernate
s "no"
```

That is not a hardware answer. logind's `Can*` methods return four values, and
only one of them is about capability:

| answer | meaning |
|---|---|
| `na` | not supported — no swap, no resume device, kernel can't |
| `no` | supported, but **polkit refuses this user** |
| `challenge` | supported, needs authentication first |
| `yes` | supported and permitted |

The refusal comes from `/usr/share/polkit-1/rules.d/com.ubuntu.desktop.rules`:

```javascript
// Disable hibernate by default in Ubuntu
polkit.addRule(function(action, subject) {
    if (action.id == "org.freedesktop.upower.hibernate" ||
         action.id == "org.freedesktop.login1.hibernate" ||
         action.id == "org.freedesktop.login1.handle-hibernate-key" ||
         action.id == "org.freedesktop.login1.hibernate-multiple-sessions") {
            return polkit.Result.NO;
    }
});
```

Unconditional, for every user, ignoring the `allow_active=yes` in the action's
own XML. [`10-mintbook-hibernate.rules`](../config/polkit/10-mintbook-hibernate.rules)
returns `YES` for the local active `sudo` user. It is named `10-` so it sorts
ahead of `com.ubuntu.desktop.rules`; polkit evaluates rules in lexical filename
order and stops at the first one that returns a result.

There is no separate `suspend-then-hibernate` polkit action — logind authorises
that operation against the hibernate actions above.

`bin/hibernate-check` reports these four answers distinctly, because reading
`no` as "the swap file is wrong" sends you to fix something that was never
broken.

## The third trap: `resume=PARTUUID=` is silently ignored

The first real hibernate on 2026-09-10 wrote its image and then failed to come
back. It left almost no trace, because every failure on this path is silent.

What the journal showed:

```
09:50:57  systemd-logind: The system will hibernate now!
09:50:58  kernel: PM: hibernation: hibernation entry
          <boot ends here>
09:58:55  <new boot id, no resume, no "PM: Image not found", nothing>
09:58:55  swapon: /swapfile: software suspend data detected.
                  Rewriting the swap signature.
```

That `swapon` line is the proof the image was written correctly — and the act
that destroyed it. A failed resume is self-erasing: the next boot enables swap,
finds the image, and overwrites it.

The cause is in `/usr/share/initramfs-tools/scripts/local-premount/resume`:

```sh
if ! local_device_setup "${resume}" "suspend/resume device" false; then exit 0; fi
DEV=$(readlink -f "$resume")          # <- the ORIGINAL string, not the resolved device
DEV=/sys/class/block/${DEV##*/}/dev
if [ -r "$DEV" ]; then read -r MAJMIN < "$DEV"; fi
if [ -z "$MAJMIN" ]; then exit 1; fi  # <- no message, no resume
```

`local_device_setup` resolves `PARTUUID=` correctly, and then the next line
throws that away and re-reads the raw string. Only `UUID=` survives, because
`init` rewrites it into a real path before the script runs:

```sh
case $RESUME in
UUID=*)
	RESUME="/dev/disk/by-uuid/${RESUME#UUID=}"
esac
```

So `readlink -f PARTUUID=bad575a6-...` yields a nonexistent path, the sysfs
lookup misses, `MAJMIN` is empty, and the script exits 1 without logging.

**`resume=` must be `UUID=` or a plain `/dev/` path.** `PARTUUID=` and
`LABEL=` look correct, pass every static check, and do nothing.

The mistake was mine and it is worth naming: `root=PARTUUID=` works on this
machine, so I matched it. But `root=` is parsed by the **kernel**, which
understands every form; `resume=` here is acted on by a **shell script** that
does not. `bin/hibernate-check` now asserts the form, not just the presence.

The offset was never the problem. Probing the raw partition confirms the swap
header sits exactly where `resume_offset` says:

```
$ blkid -p -O $((18980864 * 4096)) /dev/nvme0n1p3 -s TYPE -o value
swap
```

## The cycle that worked

2026-09-10, `systemctl hibernate` on boot `3c76e449`:

```
10:33:51  systemd-logind: The system will hibernate now!
10:33:51  kernel: PM: hibernation: hibernation entry
          PM: hibernation: Allocated 1746584 kbytes in 16.88 seconds (103.47 MB/s)
          ACPI: PM: Preparing to enter system sleep state S4
          <powered off; woken by the power button>
          ACPI: PM: Waking up from system sleep state S4
          applespi spi-APP000D:00: Received corrupted packet (crc mismatch)
          applespi spi-APP000D:00: modeswitch done.
10:35:44  kernel: PM: hibernation: hibernation exit
```

Everything between the entry and the exit carries the same timestamp because
the journal cannot flush while userspace is frozen; those lines are written
after the resume.

**The boot id did not change.** `3c76e449` started at 10:11:26, hibernated,
and is still the running boot — session `c2` came back rather than being
recreated. That is the signature of a real resume: the restored kernel *is*
the pre-hibernation kernel. A failed resume looks the opposite, and did on the
attempt before this one: a new boot id, and `swapon` rewriting the signature.

### The Apple SPI keyboard survives it

This was the open question, and the answer is in two lines that are identical
to the ones a cold boot produces:

| when | lines |
|---|---|
| cold boot, 10:11:27 | `Received corrupted packet (crc mismatch)` → `modeswitch done.` |
| hibernate resume, 10:35:43 | `Received corrupted packet (crc mismatch)` → `modeswitch done.` |

**Zero** `SPI transfer timed out` after the resume. Compare deep S3 on
2026-09-08: 47 timeouts, a failed rebind, and a reboot to get input back.

The mechanism is the one the design predicted: resume from disk boots a kernel
that probes hardware normally before restoring the image, so `applespi` gets
its working initialisation instead of the S3 path that leaves the endpoint
wedged. The input devices themselves are not re-created — `input4`/`input5`
persist from the original boot — the driver simply re-runs its modeswitch and
succeeds.

### What it looks like from the chair

Worth writing down, because it reads as a fault when it is not: after
`systemctl hibernate` the machine is **off**. Not asleep. Keys and the
trackpad do nothing, because there is nothing running to receive them. The
power button is the only way back, and pressing it resumes rather than cold
boots. On the way back, light-locker's greeter appears and wants the password,
which took about 3 seconds to paint on this cycle.

"The keyboard didn't come back, I had to press power" is the expected
experience, not a failure.

## The lid escalation fires, and then wedges

**2026-09-10, `HibernateDelaySec=2min`, on battery, lid closed.** Every link in
the chain fired, and the last one hung the machine.

```
10:59:11  kernel: PM: suspend entry (s2idle)                    <- lid
11:01:13  kernel: PM: suspend exit                              <- RTC wake, 2min on the nose
11:01:13  systemd-sleep: System returned from sleep operation 'suspend-then-hibernate'.
11:01:13  systemd-sleep: Performing sleep operation 'hibernate'...
11:01:13  kernel: PM: hibernation: hibernation entry
          <nothing, ever>
11:18:26  <cold boot, new boot id, PM: Image not found (code -22)>
```

So the escalation itself is **not** the problem. The RTC alarm woke the machine
at exactly two minutes and systemd correctly moved to the hibernate leg.

No image was written. The next boot's `swapon` said nothing about suspend data
— it just added ordinary swap — where the 09:50 failure had reported
`software suspend data detected`. The machine needed a power cycle.

It died very early. Compare how far each attempt got:

| | after `hibernation entry` |
|---|---|
| 10:33, worked | `Filesystems sync: 0.062 seconds` |
| 11:01, wedged | nothing |

That sync line is logged *after* the sync returns, and journald was still
running to record it in the working case. Its absence points at the pre-hibernate
filesystem sync never completing.

### Retracted: it is not simply "battery"

The section below concluded the power source was the discriminator. A later
test from a **text console** disproves that: on battery, from tty2, the image
saved perfectly. Keep reading for the corrected matrix in "What the TTY test
showed". The battery correlation was real but incomplete — it takes X *and*
battery together to hang the save.

### Isolated: it is the power source, not the timing

Two candidates came out of that test — that the hibernate began 70 ms after an
s2idle resume with storage still re-initialising, or that it was on battery
rather than AC. `systemctl hibernate` from a settled desktop **on battery**
separates them, and it was run at 11:30:11.

It wedged identically. No `Filesystems sync` line, no image, and a forced power
cycle. **The s2idle-wake timing is not the cause** and the settle-delay hook
proposed for it is not the fix.

The record so far:

| when | power | result |
|---|---|---|
| 09:50 | AC | image written (resume failed separately, `PARTUUID`) |
| 10:33 | AC | **worked end to end** |
| 11:01 | battery | wedged before the sync |
| 11:30 | battery | wedged before the sync |

Two for two on AC, nothing on battery.

### Where it hangs, and what is ruled out

Both failures stop between `PM: hibernation: hibernation entry` and
`Filesystems sync`. In `hibernate()` that window holds exactly two things:
`pm_prepare_console()`, which switches away from Xorg's VT, and the
`PM_HIBERNATION_PREPARE` notifier chain.

Ruled out by inspection:

- **`mintbook-power`** only writes `max_perf_pct` and `energy_perf_bias`. It
  touches no disk, no PCI link state. It had also already reasserted
  `max_perf_pct=100` at 11:19:52, so the battery cap was not even in effect.
- **NVMe runtime PM**: `power/control` is `on` and `runtime_status` is
  `active`. The drive is not being suspended underneath the sync.

So the correlation with the power source is solid and the mechanism is not.
Naming battery as the *cause* on n=2 would be overreading it; what is certain
is that hibernation is unreliable in exactly the state the feature exists to
serve.

## What the TTY test showed

Run 2026-09-10 11:49 from tty2, on battery, with `pm_debug_messages=1`,
`console_suspend=N` and console loglevel 8 so the transition printed to screen
instead of dying with the journal.

**The image saved.** The screen showed the sequence through "saving image" and
the machine powered off — the first successful save on battery, and the thing
that retires the battery-only explanation.

**The restore then failed.** On the power button the screen showed the boot
text and "restoring image", then went black and stayed black. A second power
press produced an ordinary cold boot with `PM: Image not found (code -22)`, the
image having been consumed by the attempt, and journald reporting
`corrupted or uncleanly shut down`.

### Every attempt, in one table

| time | invoked from | power | save | restore |
|---|---|---|---|---|
| 09:50 | X | AC | OK | n/a — `PARTUUID` bug |
| 10:33 | X | AC | OK | **OK** |
| 11:01 | X, 70 ms post-s2idle | battery | hang | — |
| 11:30 | X | battery | hang | — |
| 11:49 | **tty2** | battery | **OK** | hang, black screen |

Reading it honestly:

- **The save hang needs X and battery together.** X+AC saved twice, tty+battery
  saved once, X+battery hung twice. Neither variable alone accounts for it, so
  the earlier "AC-only feature" framing was wrong.
- **The restore has only ever succeeded once**, and that was the X+AC run. It
  has one failure, from tty+battery. One of each is not a pattern yet.
- The save-side window (`pm_prepare_console()` and the
  `PM_HIBERNATION_PREPARE` notifiers) is consistent with a VT switch away from
  Xorg going wrong, and something about the battery state making it go wrong.
  i915 exposes no `enable_psr`/`enable_fbc`/`enable_dc` parameters on this
  kernel, so that guess could not be checked directly.

### Not yet known: hang, or live machine with a dead display?

The restore going black is **not** proof the kernel stopped. A completed resume
with a dead panel looks identical from the chair. The journal cannot settle it
either — nothing was written after `hibernation entry`, but the machine was
powered off again quickly, possibly before journald flushed.

Distinguishing them changes everything. A dead display is a graphics problem
with ordinary workarounds; a hung restore is much worse. The test is to let the
black screen sit for two minutes, then **short-press** the power button once:
if the system is alive, logind handles that event and shuts down cleanly, and
the journal survives to prove it.

### The next single-variable test

Hibernate from **tty2 on AC**. That is the 11:49 run with only the power source
changed, and it separates the two readings of the restore failure:

- restore works → the restore problem is battery-linked
- restore fails → the restore problem is tty-linked, and the X+AC success at
  10:33 was the outlier

### The earlier diagnostic, now spent

Hibernate from a text console rather than from X:

```
Ctrl+Alt+F2, log in, then: sudo systemctl hibernate
```

Either outcome is informative. If it works, `pm_prepare_console()` switching
away from Xorg is the hang and the fix is in that direction. If it wedges, the
last kernel message stays on the screen instead of being lost with the journal,
which is the one thing no amount of log reading can recover.
`echo 1 > /sys/power/pm_debug_messages` first makes that message more specific.
`/sys/power/pm_test` is also available (`core processors platform devices
freezer`) for running the machinery without writing an image.

### Current state

`HandleLidSwitch` is back to plain `suspend` and `HibernateDelaySec` to 30min.
A lid close gets s2idle at ~1.8 W — the known cost, not a hang, because a
machine wedged with the lid shut draws ~10 W and is strictly worse.

**This means the overnight case is not solved.** ~1.8 W is about 11 hours from
full, so unplugged overnight remains unsafe. Plug in, or hibernate manually on
AC, which is proven.

## The command line

OpenCore's OpenLinuxBoot reads `GRUB_CMDLINE_LINUX_DEFAULT` out of
`/etc/default/grub` and boots the kernel EFISTUB. **`update-grub` is a no-op
here** — see [boot.md](boot.md). The installer edits that variable and nothing
else:

```
GRUB_CMDLINE_LINUX_DEFAULT="intel_iommu=off mitigations=off resume=UUID=7e20499d-3977-4253-9dfc-590530d5b1fe resume_offset=18980864"
```

`resume_offset` is counted in `PAGE_SIZE` units, while `filefrag` reports
filesystem blocks. Both are 4096 here. The installer refuses to run if they ever
stop matching, because a wrong offset resumes from garbage rather than failing.

### The expected initramfs warning

`update-initramfs` prints this, and it is correct to ignore:

```
W: initramfs-tools configuration sets RESUME=UUID=7e20499d-...
W: but no matching swap device is available.
```

The hook checks whether `RESUME` names a device of type `swap`. For a swap
*file* it never does — `RESUME` names the ext4 partition that holds the file, and
`resume_offset` locates the file within it. `scripts/local-premount/resume`
handles that case properly; the build-time hook simply does not know about it.

## Install

```bash
sudo bin/hibernate-install
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/logind-handle-lid-switch -s true
bin/hibernate-check
```

The installer writes `/sys/power/resume` as well as the command line, so
hibernation works immediately rather than only after a reboot. The two
`cmdline resume=` checks stay red until you do reboot; that is expected, and
they are what make the setting survive one. `bin/hibernate-check` is read-only
and names whichever half is missing.

The xfconf line is user-level on purpose — it needs the session bus, and running
it under `sudo` sets the key for root instead, where nothing reads it.

## What is still unproven

Settled on 2026-09-10 — resume from disk, the Apple SPI keyboard across it, and
OpenCore resuming into an image are all now observed rather than argued. What
is left:

1. **The lid path has never been exercised end to end.** Every cycle so far was
   a manual `systemctl hibernate`. Nobody has closed the lid, waited past
   `HibernateDelaySec`, and opened it. The suspend leg and the hibernate leg
   both work in isolation; the 30-minute escalation between them does not have
   a single observation behind it.
2. **The 30 minute delay is a guess**, not a measurement. At 1.8 W it costs about
   0.9 Wh per cycle, under 3% of the pack. Lower it if that reads high.
3. **Resume time was not measured cleanly.** Entry to exit was 113 s wall, but
   that includes the machine sitting powered off waiting for a person to press
   the button. Only the 16.88 s image allocation is a real number.
4. **The two deaths on deep S3** (09-05, and 09-06 going 97.8% → flat in 64
   minutes, which is ~31 W and therefore not consumption) are still unexplained.
   Unrelated to this work, but not closed.

## Undo

```bash
sudo swapoff /swapfile && sudo rm /swapfile
sudo rm /etc/systemd/sleep.conf.d/20-mintbook-hibernate.conf \
        /etc/systemd/logind.conf.d/20-mintbook-lid.conf \
        /etc/initramfs-tools/conf.d/resume
sudo cp /etc/default/grub.bak-hibernate-* /etc/default/grub
sudo cp /etc/fstab.bak-hibernate-* /etc/fstab
sudo update-initramfs -u
xfconf-query -c xfce4-power-manager -p /xfce4-power-manager/logind-handle-lid-switch -s false
sudo systemctl reload systemd-logind
```

That returns the machine to plain s2idle on the lid — which is the configuration
that flattened the battery on 2026-09-09, so undo it toward `deep` only if you
would rather have the reboot-after-wake than the overnight drain.
