# Hibernation

**Status 2026-09-10, 21:10: works on AC in the default `platform` mode.
`HibernateMode=shutdown` never restores (0 for 3, AC included). On battery, no
`platform`-mode cycle has ever completed.**

- **On AC in `platform` mode, 7 for 7** — four saves, three restores (the last
  one, Test E0, with the debug command line), from both X and a text console,
  Apple SPI keyboard intact. `systemctl hibernate` on AC
  is reliable. ~~On AC, 5 for 5~~ was true only until Test D. A
  `shutdown`-mode cycle on AC saved and then failed to restore.
- **On battery, 0 for 4 full cycles.** ~~From X it hangs on the save; from a
  text console it saves and then hangs on the restore.~~ Two battery saves are
  now **known to have finished**: 11:49 from tty2, and Test B at 19:18 from X
  in `HibernateMode=shutdown`, proved by the swap header. Neither restored.
  Test B's restore died before userspace and left no journal, and it did so
  with no ACPI S4 code involved. The two X "save hangs" (11:01, 11:30) left the
  same evidence a consumed image leaves, so they may have been restore failures
  too. ~~**The restore is now the prime suspect.** Test C restored a battery
  save on AC, and it failed too, so the power source at restore time is not
  the cause.~~ **Retracted after Test D:** a `shutdown`-mode save and restore
  entirely on AC failed the same way. So `HibernateMode=shutdown` does not
  restore on this machine at all (0 for 3), and Tests B and C say nothing
  about battery. The battery evidence is back to one clean failure, 11:49
  (`platform` mode, tty2), plus two ambiguous ones. `shutdown` mode is out as
  a fix. **Test E (21:23) then ran the real case in `platform` mode, on
  battery, and filmed it.** The save completed, and the boot kernel loaded
  the image, stopped the EC, parked the CPUs, and handed over. The restored
  kernel never came back. The battery failure is therefore, in that run, a
  death in the restored kernel's first steps after the jump. **Test F (21:43)
  repeated it with the Smart Battery driver unloaded, and it failed the same
  way**, so `sbs` is out. So is the CPU policy (E and F used different
  profiles). The mechanism is not established.
- **Narrowed on 2026-09-10 evening.** A `pm_test=core` run on battery from X
  got through the whole save path except the image: VT switch, notifiers,
  sync, freeze, allocation, device freeze and ACPI `_PTS(4)`. It came back
  unaided. ~~The hang therefore more likely sits in the snapshot copy, the
  image write, or the S4 power-off itself.~~ Test B then showed that, in
  `shutdown` mode, the copy and the write finish too. One run each; see
  "Test A" and "Test B".
- Charger out changes only the CPU policy (1,623 settings diffed), and the
  firmware's `_PTS`/`_WAK` do not branch on the power source.
- **The overnight case is therefore not solved.** `suspend-then-hibernate`
  hibernates from s2idle with X active, on battery — the exact combination that
  hangs. The lid is back on plain `suspend` at ~1.8 W, about eleven hours, so
  unplugged overnight is still unsafe. Plug in, or hibernate by hand on AC.

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

### Why s2idle costs that much here, and why it cannot be tuned down

The obvious follow-up is to make s2idle cheaper instead of working around it.
That was checked on 2026-09-10 and there is **no headroom: this platform has no
S0ix at all.**

s2idle is only cheap on hardware with Low Power S0 Idle, where the firmware and
the SoC drop the platform into a genuine low-power state. Three independent
checks say this machine has none of that:

| check | result |
|---|---|
| ACPI `LPIT` table (how firmware reports S0ix residency) | **absent** — tables are APIC DMAR DSDT ECDT FACP FACS HPET MCFG SBST SSDT1-7 |
| FADT Low Power S0 Idle flag | not set — the kernel logs nothing about low-power S0, and defaulted `mem_sleep` to `deep` rather than `s2idle` |
| `intel_pmc_core`, the S0ix reporter | supports CPU models `0x4E` (Skylake) and later. This is a Core M-5Y31, **model `0x3D`**, Broadwell |

So s2idle here is plain `freeze`: processes stopped, devices asked to suspend,
CPU idling in ordinary C-states, and every rail still up. ~1.8 W is simply what
that costs. There is no low-power state being missed and no knob that reaches
one.

The `intel_pch_thermal` warning that appears on some suspends —
`CPU-PCH current temp [53C] higher than the threshold temp [50C], S0ix might
fail` — is the Wildcat Point driver's generic message. It is not evidence that
S0ix works here, and chasing it would have been wasted effort.

For scale, the three sleep states on this machine:

| state | draw | a full 34.1 Wh pack lasts |
|---|---|---|
| awake, idle | ~6 W | ~6 h |
| s2idle (`freeze`) | ~1.8 W | ~19 h |
| deep S3 | ~0.08 W | weeks |
| hibernated | 0 W | indefinitely |

Note what that means for the original failure: at **full** charge s2idle would
have survived the night with hours to spare. 2026-09-09 died because the lid
closed at 54%, which is only about ten hours. Charging above ~70% before bed is
a real, if unsatisfying, mitigation.

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

~~No image was written.~~ The next boot's `swapon` said nothing about suspend data
— it just added ordinary swap — where the 09:50 failure had reported
`software suspend data detected`. The machine needed a power cycle.

**"No image was written" is retracted (2026-09-10 evening).** A silent
`swapon` also follows an image that was written and then consumed by a restore
attempt, and that restore attempt runs in the initramfs where the journal
cannot see it. Test B produced exactly this evidence after a save that is
proven to have finished. The 11:01 header has since been overwritten, so which
of the two happened here cannot be recovered.

It died very early. Compare how far each attempt got:

| | after `hibernation entry` |
|---|---|
| 10:33, worked | `Filesystems sync: 0.062 seconds` |
| 11:01, wedged | nothing |

~~That sync line is logged *after* the sync returns, and journald was still
running to record it in the working case. Its absence points at the pre-hibernate
filesystem sync never completing.~~

**Retracted 2026-09-10 evening — the comparison above cannot localise
anything.** journald does not record `Filesystems sync` before the freeze even
when hibernation *works*. From the 12:50 AC cycle, which succeeded, with
journald's own receive time next to the kernel's printk time:

```
journald received   printk     message
12:50:35.954        3564.315   PM: hibernation: hibernation entry
12:51:36.670        3564.409   Filesystems sync: 0.039 seconds       <- a minute later, after resume
12:51:36.740        3564.409   Freezing user space processes
12:51:37.191        3577.304   PM: hibernation: hibernation exit
```

The sync finished 94 ms after entry, and journald did not pick up the line
until the machine was back. `entry` is the last line journald reliably catches
before userspace freezes. So a failed run that ends at `entry` looks exactly
the same as a working run would if you cut the power at that moment. Its
absence says only that the machine never *resumed*. It says nothing about
whether the hang came before the sync, during the image write, or at power-off.

### Every attempt, and what they add up to

Six cycles on 2026-09-10. Two variables moved: which VT was active when
hibernation started, and whether the charger was in.

| time | invoked from | power | save | restore |
|---|---|---|---|---|
| 09:50 | X | AC | OK | n/a — `PARTUUID` bug |
| 10:33 | X | AC | OK | **OK** |
| 11:01 | X, 70 ms post-s2idle | battery | hang | — |
| 11:30 | X | battery | hang | — |
| 11:49 | tty2 | battery | **OK** | hang, black screen |
| 12:50 | tty2 | AC | **OK** | **OK** |
| 18:53 | X, `pm_test=core` | battery | **early path OK** (no image by design) | — |
| 19:18 | X, `mode=shutdown` | battery | **OK** — proved by the swap header | **failed** — consumed by a boot that left no journal |
| 20:50 | X, `mode=shutdown` | battery | **OK** — new header crc | **failed on AC** — "error" flashed past |
| 21:00 | X, `mode=shutdown` | **AC** | **OK** — new header crc | **failed on AC** — image loaded, died after `Suspending console(s)` |
| 21:16 | X, `platform`, debug cmdline | AC | **OK** | **OK** — same boot id, `returned result=success` |
| 21:23 | X, `platform`, debug cmdline | battery | **OK** — image found and loaded | **failed** — boot kernel reached the jump, restored kernel never returned |
| 21:43 | X, `platform`, `sbs` unloaded | battery | **OK** — image loaded | **failed** — same as 21:23 |

**On AC nothing has ever failed** — three saves, two restores. **On battery
nothing has ever fully succeeded.** The active VT does not decide whether it
fails, only where:

- ~~**X + battery** hangs on the save, before the image is complete. The next
  boot found no image. before `Filesystems sync` ever returns~~ — retracted
  twice. The journal cannot place the hang, and "the next boot found no image"
  is also what a consumed image looks like. Test B saved from X on battery, and
  the image was complete. Whether 11:01 and 11:30 were save or restore
  failures is unrecoverable.
- **tty + battery** saves cleanly and then hangs on the restore, after
  "restoring image", with a black screen.

Two earlier conclusions in this file were wrong and are left above with their
retractions: that the s2idle-wake timing mattered (killed by 11:30), and that
the power source alone was the discriminator (killed by 11:49). The corrected
statement is narrower: **battery is present in every failure, and no single
other variable is.**

### Where each side hangs

~~The save-side failures stop between `PM: hibernation: hibernation entry` and
`Filesystems sync`. That window holds exactly `pm_prepare_console()`, which
switches away from Xorg's VT, and the `PM_HIBERNATION_PREPARE` notifier chain.
Starting from a text console skips the interesting half of that, and starting
from a text console is exactly what fixed the save — but only far enough to
reach the next failure.~~

**Retracted 2026-09-10 evening.** That window was read off the journal, and the
journal never records `Filesystems sync` before the freeze, even on a cycle that
works (see "The lid escalation fires, and then wedges"). What the evidence
actually supports is wider: the save-side failures stop somewhere after
`hibernation entry` and before the image signature is written, because the next
boot found no image. That span covers the VT switch, the notifiers, the sync,
the freeze, the 10–17 s image allocation, the device freeze, the ACPI
`_PTS(4)` call that `platform` mode makes before the snapshot, and the whole
image write. The VT theory was only ever one candidate among those, and
tty-versus-X rests on a single tty run on battery.

The restore-side failure is one observation, so it is not yet a pattern. It is
also **not proof the kernel stopped**: a completed resume with a dead panel is
indistinguishable from the chair, and the machine was powered off again before
journald could flush. ~~Letting the black screen sit two minutes and then
short-pressing power would decide it, since a live system shuts down cleanly on
that event and leaves a journal behind.~~ That probe cannot work here:
xfce4-power-manager holds `handle-power-key` and answers with a dialog nobody
can see. Its replacement is in `bin/hibernate-trial`, which syncs a `returned`
line to disk as soon as it is thawed. Test B used it, and the line is absent,
so that restore did die before userspace (see "Test B").

### Ruled out by inspection

- **`mintbook-power`** writes only `max_perf_pct` and `energy_perf_bias`. At the
  11:01 failure it had already applied `profile=balanced max_perf_pct=100
  epb=8`, which is what AC gets, and it hung anyway.
- **NVMe runtime PM**: `power/control=on`, `runtime_status=active`.
- **Audio codec runtime PM**: `snd_hda_intel power_save=0`.
- **No TLP and no laptop-mode-tools** are installed.
- **pm-utils *is* installed**, which that check missed. Its
  `/usr/lib/pm-utils/power.d/` ships exactly the battery tunings a hang like
  this would suggest: `laptop-mode` (laptop_mode=5, 10-minute writeback),
  `pci_devices` (runtime PM `auto` on Wi-Fi and audio), `pcie_aspm`
  (`powersave`), and `wireless`. Checked 2026-09-10 and **nothing ever runs
  them.** Only `pm-powersave` calls those hooks, and nothing calls
  `pm-powersave`. No udev rule, systemd unit or D-Bus service refers to it,
  acpid and acpi-support are not installed, and there is no
  `/var/log/pm-powersave.log`. The one other hook, the hdparm script in
  `/usr/lib/systemd/system-sleep/`, acts only on `post`, and only on ATA disks.
- ~~i915 exposes no `enable_psr`/`enable_fbc`/`enable_dc` on this kernel, so the
  most obvious remaining suspect could not be checked directly.~~ **Corrected
  2026-09-10 evening:** those parameters do exist, but they're root-only, under
  `/sys/kernel/debug/dri/0000:00:02.0/i915_params/` (for example
  `enable_psr=-1` and `enable_fbc=1`). `bin/power-snapshot` reads them. What they
  settle:
  - **PSR is ruled out by the hardware.** The eDP panel reports
    `Sink support: PSR = no`, so PSR never engages whatever the parameter says.
  - **DMC/DC states do not apply.** Broadwell has no DMC firmware; that
    arrived with Skylake. No `i915_dmc_info` file exists.
  - **FBC is live on AC** (`FBC enabled`, `Compressing: yes`). Whether it
    changes on battery is what the AC/battery diff is for.

### What changes when the charger comes out (measured)

`bin/power-snapshot` was run on AC at 17:57, pulled at 18:02:58, then run again
immediately and at +3 minutes (2026-09-10). It covers 1,623 keys: runtime PM
and wakeup for all 614 devices that have it, PCIe ASPM and link state,
pstate/cpufreq/EPB, backlight, DRM connectors, i915 debugfs
(FBC/PSR/DRRS/power domains/runtime PM), i915/HDA/usbcore/nvme module
parameters, vm writeback, and the xfce4-power-manager, X DPMS and PPD session
state.

**Almost nothing moves.** The whole diff, apart from the supply's own
`online`/`status`:

| key | AC | battery |
|---|---|---|
| PPD profile | balanced | power-saver |
| `intel_pstate/max_perf_pct` | 100 | 70 |
| EPB, all four CPUs | 6 | 15 |
| `scaling_max_freq` | 2.4 GHz | 1.68 GHz |
| i915 FBC `Compressing` | yes | no *(unverified: see below)* |

The CPU policy rows are all `mintbook-power` responding to the charger. No
runtime-PM control or status changed on any device. Neither did ASPM, the
backlight (`acpi_video0` at 40), the writeback sysctls, DPMS or any xfconf key.
The +3 minute snapshot matched the immediate one, so xfce4-power-manager applies
nothing on a delay either.

The FBC row is the only display difference. It is **not yet trusted**: the AC
snapshot and both battery snapshots were each taken with a pkexec dialog on
screen, and FBC drops compression whenever the front buffer is redrawn. It
stayed at `no` at +3 minutes with the GPU idle, which argues it is real, but
one pair of samples is not enough to say so.

This matters for the 11:01 failure. It happened on battery while
`mintbook-power` held `balanced max_perf_pct=100 epb=8`. That value comes from
a profile request made on battery, and on this evening's log the same
`balanced ... ac=0 ... epb=8` line recurs whenever the profile is picked by
hand. So at 11:01 the CPU policy was within one EPB step of AC. If that
reading is right, the software configuration all but ruled itself out, and the
remaining difference is the physical power source: firmware, the EC, and the
Smart Battery behind it. The 11:01 journal has since rotated away, so this
rests on the earlier notes above rather than on a log that can be re-read.

### EC traffic: busy, but the same on AC

The EC's GPE (`0x4e`, from the boot log `ACPI: EC: GPE=0x4e`) looked like a
storm at first: 1,306 in 30 s on battery. It is not firmware noise. It is
`bin/panel-battery` polling BAT0 every 5 s. BAT0 is a Smart Battery behind the
EC's SMBus (`sbs`/`sbshc`), and the first attribute read refreshes the whole
cache over that bus. Measured 2026-09-10:

| | burst every 5 s | GPEs per BAT0 refresh | refresh time |
|---|---|---|---|
| battery (Discharging) | 161–165 | 161–165 | 48–54 ms |
| AC (Charging) | 126–129 | 126–127 | 38–44 ms |

Between bursts the GPE count does not move at all. The pattern is the same on
AC, so the EC being busy is **not a battery-only difference** and does not
explain the correlation. The panel does keep the EC SMBus busy about 1% of the
time, which is worth remembering if a suspend or resume ever has to wait on it.

### Test A: the early save path completes on battery, from X

2026-09-10 18:53, `pkexec bin/hibernate-trial --pm-test core`, started from X
(vt7) on battery, PPD on power-saver. `pm_test=core` runs every step of the
save except the snapshot copy, the image write and the power-off. It holds
for 5 s at the point where the image would be taken, then unwinds.

```
[4566.80]  PM: hibernation: hibernation entry
[4567.10]  Filesystems sync: 0.091 seconds
[4591.60]  PM: hibernation: Allocated 1780908 kbytes in 24.49 seconds (72.71 MB/s)
[4592.36]  ACPI: PM: Preparing to enter system sleep state S4     <- _PTS(4), EC.ECSS=4
[4597.54]  ACPI: PM: Waking up from system sleep state S4
[4598.70]  PM: hibernation: hibernation exit
```

**It came back on its own, 38 s wall clock, same boot id.** The kernel log
carries no warnings. applespi shows the same `crc mismatch` → `modeswitch done`
pair as a healthy resume. `pm_test` was back to `none` afterwards.

So on battery, from X, all of these worked: the VT switch away from Xorg, the
`PM_HIBERNATION_PREPARE` notifiers, the sync, the freeze, the image
allocation, the device freeze, and the firmware's `_PTS(4)`. That is the span
the old theory blamed. **This is one run.** It doesn't exclude an intermittent
early hang, but the two X-on-battery failures now more likely stopped later:
- in the snapshot copy (`swsusp_arch_suspend`)
- in the device thaw that follows it
- in the image write
- or in the real S4 power-off, where the EC gets `ECSS=4` and SLP_TYP and
  is expected to cut power

One number moved with the CPU policy: the allocation ran at **72.7 MB/s**,
against 103–134 MB/s on AC. That is 24.5 s instead of 10–17 s. It doesn't
explain a hang, but every stage on battery runs for longer.

### Test B: a complete image on battery, from X, and a restore that never came back

2026-09-10 19:18, `pkexec bin/hibernate-trial --mode shutdown`, started from X
(vt7) on battery. `HibernateMode=shutdown` writes the image and then powers off
with no ACPI S4. That means no `_PTS(4)` and no `ECSS=4` on the way down, and
no `_WAK` on the way back. The mode is the one variable that changed against
the failing X-on-battery runs.

The journal says only this:

```
19:18:50  hibernate-trial: start ac=0 bat=Discharging vt=7 pm_test=none mode=shutdown
19:18:51  kernel: PM: hibernation: hibernation entry
          <boot e47e3f24 ends>
19:55:09  <boot 0: PM: Image not found (code -22); swapon silent>
```

The user reported **two restarts**. On journal evidence alone that looks
exactly like the 11:01 and 11:30 failures. The swap header does not:

```
$ pkexec dd if=/swapfile bs=4096 count=1   # swsusp_header, last 40 bytes
sig      = SWAPSPACE2
orig_sig = SWAPSPACE2
flags    = 0x4        platform=0  crc32=1
image    = 18980865   resume_offset + 1: the first page after the header
crc32    = 0x685bf472
```

The kernel writes `flags`, `image` and `crc32` in `mark_swapfiles()`. That is
the last step of the save, after every image page is on disk. A boot that
finds the image puts back only the signature (`swsusp_check`: "Reset swap
signature now"), and swapon's own rewrite touches only the signature too, so
the other fields outlive the image. `platform=0` marks a `shutdown`-mode
save. Every other image today was written in `platform` mode, so this header is
Test B's.

What that establishes:

1. **The save completed.** This is the first battery hibernate started from X
   that is known to have finished writing its image.
2. **A boot found the image and consumed it, without leaving a journal.** That
   was restart one. Resume runs in the initramfs before root is mounted, so a
   restore that dies there writes nothing. Restart two is boot 0, which found
   no image.
3. **The restored system never got back to userspace.** A successful restore
   keeps the boot id, and `e47e3f24` ends at 19:18:51. `hibernate-trial` also
   syncs a `returned` line to disk the moment it is thawed, and there is none.
   So this was not a live system behind a dead panel. It died in the restore
   itself: the image load, the jump into the image, or the resume of devices
   before thaw. Which of those is not known yet.
4. **The restore failed without any ACPI S4 code.** A `platform=0` image is
   restored with no platform hooks, so `_WAK` and the EC's S4 handling are
   ruled out for the restore side, at least in this mode.

**What this does to the earlier runs.** 11:01 and 11:30 were written up as save
hangs because the next boot found no image and `swapon` said nothing. Test B
leaves exactly that evidence after a save that finished. Their headers have
since been overwritten, so they cannot be re-read. They may have been save
hangs, or complete saves followed by a restore attempt that nobody noticed as a
separate boot. The status line "never completed on battery" is now better read
as **never restored on battery**: two battery saves are known to have finished
(11:49 from tty2 in `platform` mode, and this one), and neither came back.

This is one run. It does not show that `platform`-mode saves finish on battery.
How restart one looked from the chair is still to be written down.

### Test C: the same battery save, restored on AC — still fails

2026-09-10 20:50. Same as Test B (`--mode shutdown`, from X, on battery,
46%). This time the charger went in **while the machine was off**, and power
was pressed only after that, so the restore ran on AC.

- **The save completed again.** The header changed from Test B's
  `crc32 = 0x685bf472` to `0xac44afe6`: `flags = 0x4` (platform bit clear) and
  `image = 18980865`. That is a new, complete image.
- **Plugging in while off put a battery graphic on screen.** That is the
  firmware reacting to the charger; the OS was not running.
- **The restore failed on AC.** From the chair: it "tried to resume",
  something flashed past too fast to read, and **the word "error" was probably
  on screen**. A full restart was needed. The journal agrees: the boot ends at
  `hibernation entry` (20:50:38), there is no `returned` line, the next boot
  (20:53:20) reports `Image not found`, and the header's signature is back to
  `SWAPSPACE2`, so a boot consumed the image. The whole sequence took 2.7
  minutes.

~~So **the power source at restore time is not what breaks it.** An image saved
on battery fails to restore on AC as well. One run.~~ **Retracted by Test D.**
A `shutdown`-mode image saved *and* restored on AC fails too, so this run
isolates nothing about power. It only adds to the `shutdown`-mode failures.

**A confound this exposes.** Both restores that ever worked (10:33 and 12:50)
were `platform`-mode images saved on AC. Tests B and C were `shutdown`-mode
images saved on battery. No `shutdown`-mode image has been restored on this
machine at all, so "saved on battery" and "saved in shutdown mode" cannot yet
be told apart. The only failure without that confound is 11:49 (battery,
`platform`, tty2). The control is a `shutdown`-mode save and restore entirely
on AC.

### Test D: `shutdown` mode fails on AC too — the control

2026-09-10 21:00, `--mode shutdown`, from X, **on AC throughout**, and the
restore filmed.

- **The save completed.** New header, `crc32 = 0x57ff1fad`, `flags = 0x4`.
  After the failed resume the signature was back to `SWAPSPACE2`, and the next
  boot (21:02:19) found no image.
- **The restore failed on AC.** There is no `returned` line, and the boot id
  changed.
- **The film shows where.** The boot kernel's initramfs found and loaded the
  image without complaint. Transcribed from the photo:

  ```
  [2.089] PM: hibernation: resume from hibernation
  [2.113] Freezing user space processes ... completed
  [2.177] PM: Using 3 thread(s) for lzo decompression
  [2.177] PM: Loading and decompressing image data (346121 pages)...
  [2.342] PM: Image loading progress:   0%
  ...
  [7.044] PM: Image loading progress: 100%
  [7.046] PM: Image loading done
  [7.048] PM: hibernation: Read 1384484 kbytes in 4.86 seconds (284.87 MB/s)
  [7.050] printk: Suspending console(s) (use no_console_suspend to debug)
          <frozen here>
  ```

  So the image is read and decompressed correctly, with no CRC or
  decompression error. What dies comes after the boot kernel silences its
  console. That is either the boot kernel quiescing its own devices and
  parking the other CPUs, or the jump into the image, or the restored kernel
  resuming devices before its display is back. The boot kernel prints nothing
  past that line unless `no_console_suspend` is on its command line.

**What this settles.** `HibernateMode=shutdown` has restored **0 times out of
3** on this machine, on AC and on battery alike. It is not a fix, and Tests B
and C cannot speak to the battery question. Every restore that ever worked here
was a `platform`-mode image.

**A candidate mechanism, not yet tested.** `platform` mode does two things
around a restore that `shutdown` mode skips:
- in the boot kernel, just before the jump, ACPI `pre_restore` disables all
  GPEs and suspends EC transactions
- in the restored kernel, the platform leave/finish hooks run `_WAK` and
  re-enable ACPI state

On a machine whose EC raises a GPE burst every 5 s (see "EC traffic"), an
event arriving across that jump is a plausible way to die. That fits all
three `shutdown`-mode failures. It says nothing yet about why the one clean
`platform`-mode battery run (11:49) failed.

### Test E0: the AC control with the debug command line — restores

2026-09-10 21:16, `pkexec bin/hibernate-trial` (default `platform` mode),
from X, on AC, booted with `no_console_suspend pm_debug_messages`, and filmed.
This run checks that the new command line does not break a restore on its
own, and records what a working restore looks like, for comparison with
battery.

**It restored.** The boot id was `29bf1747` before and after.
`hibernate-trial` logged `returned result=success` at 21:20:04. The kernel
log for the cycle is complete, from both sides of the image:

```
[273.66] PM: hibernation: hibernation entry
[273.89] Filesystems sync: 0.029 seconds
[289.42] PM: hibernation: Allocated 1517996 kbytes in 15.52 seconds (97.80 MB/s)
[290.21] PM: noirq freeze of devices complete after 2.559 msecs
[290.21] ACPI: PM: Preparing to enter system sleep state S4
[290.36] Disabling non-boot CPUs ...          CPU 3, 2, 1 offline
[290.37] PM: hibernation: Creating image      377047 pages to copy
         -- image written, powered off, restored --
[290.37] ACPI: PM: Restoring platform NVS memory
[290.37] Enabling non-boot CPUs ...           CPU 1, 2, 3 up
[290.38] ACPI: PM: Waking up from system sleep state S4
[292.02] PM: restore of devices complete after 1439.589 msecs
[292.03] PM: hibernation: Hibernation image restored successfully.
[292.63] PM: hibernation: hibernation exit
```

applespi shows the usual `crc mismatch` → `modeswitch done` pair and no SPI
timeouts. The `error -2` lines around the restore are brcmfmac and facetimehd
looking for optional firmware files as they re-probe. They look like
ordinary firmware-probe noise, not a fault, but they were not compared
against a cold boot.

`platform`-mode restores on AC are now **3 for 3**, including one with the
debug command line. So if Test E fails on battery, the command line is not
the reason.

### Test E: `platform` mode on battery — the boot kernel hands over, the restored kernel never returns

2026-09-10 21:23, `pkexec bin/hibernate-trial` (default `platform` mode),
from X, on battery at 66%, booted with the debug command line, and filmed. PPD
happened to be on `balanced` (`max_perf_pct=100`), so the CPU policy was
close to AC's for this save.

- **The journal** ends at the trial's `start ac=0 bat=Discharging ...
  mode=default` line (21:23:22). There is no `returned` line. The next boot
  (21:25:24) reports `Image not found`.
- **The swap header** reads `flags = 0x5` (platform and CRC32),
  `crc32 = 0x8e29f4f2`, with the signature back to `SWAPSPACE2`. That is a
  `platform`-mode image, consumed by the failed restore. It is Test E's:
  E0's image had already been consumed by its own successful restore, so
  Test E's save wrote the most recent header.
- **The film settles where it died.** Transcribed from the last frame:

  ```
  [7.664] PM: Image loading done
  [7.664] PM: hibernation: Read 1497728 kbytes in 5.49 seconds (275.82 MB/s)
  [8.423] ACPI: EC: interrupt blocked
  [8.424] ACPI: EC: event blocked
  [8.424] ACPI: EC: EC stopped
  [8.429] Disabling non-boot CPUs ...
  [8.440] smpboot: CPU 3 is now offline
  [8.449] smpboot: CPU 2 is now offline
  [8.456] smpboot: CPU 1 is now offline
          <cursor; nothing more>
  ```

With `no_console_suspend`, the boot kernel printed its whole side. It loaded
all 374,432 pages of the image. Then `platform` mode's `pre_restore` stopped
the EC (the step `shutdown` mode skips), and the other CPUs went offline. After
CPU 1 there is only `syscore_suspend` and the jump into the image, and neither
prints. **So on battery the boot kernel reaches the hand-over, and the
restored kernel dies after it.** That rules out the image load, the
decompression and the boot kernel's device quiesce.

On AC, E0's restored kernel went on to log this sequence:
1. `Restoring platform NVS memory`
2. `Enabling non-boot CPUs`
3. `Waking up from system sleep state S4` (`_WAK`)
4. a 1.44 s device restore

Test E died somewhere in that sequence, before i915 had lit the panel. The
restored kernel's console is i915's, so it is blind until then.

**What this says about the battery failure, in `platform` mode:**
- **The save completed.** The initramfs found and loaded a complete image.
  So this run was a restore failure, not a save hang.
- **The CPU policy is a weaker suspect.** The save ran at `max_perf_pct=100`,
  as on AC.
- **The candidates** are what the restored kernel does differently on battery
  right after it wakes: the Smart Battery driver's resume (`sbs` refreshes
  the whole battery over the EC's SMBus, about 160 EC transactions), EC events
  that queued while discharging and fire when the EC is re-enabled, and
  `_WAK`'s `PWRS = EC.EACP` → `PNOT()` CPU notifications arriving while the
  CPUs come back.
- This is one run.

### Test F: the Smart Battery driver taken out — same failure

2026-09-10 21:43, `pkexec bin/hibernate-trial --unload sbs` (default
`platform` mode), from X, on battery at 53%, and filmed. The one change
against Test E is that `sbs` was unloaded for the cycle. PPD was on
`power-saver` (`max_perf_pct=70`) this time; Test E ran on `balanced` at 100.

- **`sbs` really was out.** The start line reads `start ac=0 bat=? ...
  unload=sbs`. `bat=?` means `BAT0/status` did not exist when the line was
  written, and the trial refuses to hibernate if the module is still loaded.
  `modprobe -r sbs` should also have taken `sbshc`, since nothing else held
  it, but that was not logged.
- **The restore failed.** There is no `returned` line. The next boot
  (21:45:29) reports `Image not found` and loads `sbs`/`sbshc` normally.
- **The film shows the same ending as Test E**: image loaded, EC stopped,
  CPUs 3–2–1 offline, then nothing. This is from the user's viewing; the
  frame was not transcribed.

**So the Smart Battery driver's resume is not what kills the restored
kernel.** It is ruled out, on one run. The CPU policy is now out for this
failure too: the restore died with `balanced`/100 (E) and with
`power-saver`/70 (F).

What is left between "the boot kernel hands over" and "the restored kernel
shows a panel" that could care about the power source:
- the ACPI NVS restore
- the EC being re-enabled with events that queued while discharging
- `_WAK`'s `PWRS = EC.EACP` → `PNOT()` notifies as the CPUs come back
- any device whose resume path the firmware treats differently on battery

None of those has been separated yet. A cheaper split comes first: whether
the battery matters at **save** time or at **restore** time, in `platform`
mode. That has never been tested. (Test C tried it, in `shutdown` mode,
which never restores at all.)

### The firmware's sleep methods do not look at the power source

In `platform` hibernate mode, the default, the kernel calls the firmware's
`_PTS(4)` before the snapshot and its `_WAK` after restore. That code runs on
both the save path and the restore path, so it was worth checking for a
battery branch. The tables were dumped and decompiled on 2026-09-10.

- **The running DSDT is ours, not Apple's.** The boot log shows
  `ACPI: Table Upgrade: override [DSDT-APPLE - MacBook]`. That is the Bluetooth
  override ([bluetooth.md](bluetooth.md)), which only rewrites `SSDC._STA`.
  `_PTS`, `_TTS` and `_WAK` are identical to the pre-patch dump in
  `/var/lib/macbook-bt-ssdc/dsdt.dsl`; the only differences are iasl spelling
  `0x00` versus `Zero`.
- **Linux takes the Darwin branches.** `OSDW()` is true, because the kernel
  answers `_OSI("Darwin")` on Apple hardware. The evidence is that `SMB0._STA`
  returns present only under Darwin, and `sbs` is bound to it.
- **`_PTS(4)`** writes port 80, sets `GP13 = 0`, sleeps 150 ms, and writes
  `EC.ECSS = 4`, which tells the EC the target sleep state. Nothing else runs
  under Darwin.
- **`_WAK`** writes `ECSS = 0`, re-reads the lid, sets two GPIOs, copies
  `PWRS = EC.EACP`, and calls `PNOT()`. `PNOT()` only sends CPU
  performance/C-state notifies, and `_PPC` returns `CPLT`, not `PWRS`.

**There is no branch on `PWRS` or `EACP` in any of them.** At the AML level,
S4 entry and wake run the same code on battery as on AC. The only
power-dependent AML is `_Q21` (the charger event) and the battery's own `UBST`.
What the EC firmware does with `ECSS = 4` while discharging is invisible from
here. That is the one place an ACPI S4 explanation could still live, and only
a test that skips it (`HibernateMode=shutdown`) can speak to it.

So the mechanism behind the battery correlation is **not established**. What is
established is the shape of it, at 5 successes on AC and 0 clean cycles on
battery.

### What this means for the feature

The case hibernation was built for is the overnight one, and overnight the
machine is on battery. `suspend-then-hibernate` wakes from s2idle with X still
the active VT and hibernates from there — precisely the X + battery combination
that hangs, twice out of two.

**So the overnight problem is not solved.** What does work, reliably, is
`systemctl hibernate` on AC.

### Current state

`HandleLidSwitch` is back to plain `suspend` and `HibernateDelaySec` to 30min.
A lid close costs the known ~1.8 W rather than risking a hang, because a machine
wedged with the lid shut draws ~10 W and is strictly worse. At ~1.8 W a full
charge is about eleven hours, so **unplugged overnight is still unsafe**. Plug
in, or hibernate by hand on AC before closing the lid.

## The command line

OpenCore's OpenLinuxBoot reads `GRUB_CMDLINE_LINUX_DEFAULT` out of
`/etc/default/grub` and boots the kernel EFISTUB. **`update-grub` is a no-op
here** — see [boot.md](boot.md). The installer edits that variable and nothing
else:

```
GRUB_CMDLINE_LINUX_DEFAULT="intel_iommu=off mitigations=off resume=UUID=7e20499d-3977-4253-9dfc-590530d5b1fe resume_offset=18980864"
```

**Temporary, from 2026-09-10 21:09: `no_console_suspend pm_debug_messages`
are appended** for the battery investigation. Test D's restore froze on the
boot kernel's `printk: Suspending console(s)`. Without `no_console_suspend`
the boot kernel prints nothing through its device quiesce, its CPU parking
or the jump into the image, and that is exactly where restores die here.
~~`pm_debug_messages` turns on the PM core's own progress lines from the first
instant of boot, so the restore path in the initramfs prints them too.~~
**Corrected after the reboot (verified: both are in `/proc/cmdline`,
`pm_debug_messages=1`, `console_suspend=N`).** `pm_debug_messages` does turn
the PM core's debug lines on from the first instant of boot, but it prints
them at `KERN_DEBUG`. A line reaches the screen only if its level is below
the console loglevel, which is the kernel default of 7 in the initramfs and 4
after Ubuntu's sysctl. So those lines go to the ring buffer, **not the
screen**. Getting them on screen would take `loglevel=8`.
`no_console_suspend` still does its job: info-level lines past
`Suspending console(s)` will show, such as the CPUs going offline before the
jump. The
runtime knobs `bin/hibernate-trial` sets cannot reach that far, because the
boot kernel never runs the trial. These are debug-only; **remove them when
the investigation ends**. The pre-change file is
`/etc/default/grub.bak-debug-*`.

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
