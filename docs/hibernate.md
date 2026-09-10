# Hibernation

**Status 2026-09-10: hibernation writes an image. Resume has failed once and is
still unverified.**

- Writing the image **works**. A `systemctl hibernate` at 09:50:58 entered
  hibernation and powered the machine off with a complete image on `/swapfile`.
- Resuming **did not happen**. The machine cold-booted with a new boot id and
  `swapon` then reported `software suspend data detected. Rewriting the swap
  signature`, destroying the image. One session was lost.
- The cause was `resume=PARTUUID=`, which initramfs-tools silently ignores. It
  is fixed (`resume=UUID=`) and the resume path has been replayed by hand
  end-to-end, but **no successful resume has been observed yet**, so the Apple
  SPI question below is still open.

See "The third trap" and "What is still unproven".

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

1. **Resume from disk has been attempted once and failed** (see "The third
   trap"). The cause is understood and fixed, and the script's logic has been
   replayed by hand against the live config — `readlink` resolves, `MAJMIN`
   comes out `259:3`, and `blkid` finds the swap area at the offset. But a
   replay is not a resume. The whole design still rests on an event nobody has
   observed.
2. **Whether the Apple SPI keyboard and trackpad come back after a hibernate
   resume.** The reasoning says yes — resume is a cold boot and `applespi`
   re-probes over PIO — but reasoning is what predicted the s2idle battery cost
   too. Verify with `bin/input-check` immediately after the first resume.
3. **Whether Apple's firmware and OpenCore resume cleanly into an image.** Not
   tested. If OpenCore's picker interferes, the fallback is a normal cold boot
   and a lost session, not a broken disk.
4. **The 30 minute delay is a guess**, not a measurement. At 1.8 W it costs about
   0.9 Wh per cycle, which is under 3% of the pack. Lower it if that reads high.

Do not record this as working until 1 and 2 have been observed.

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
