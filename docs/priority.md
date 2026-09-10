# Application priority — 2026-09-09

The foreground app gets its ordinary thread priorities; other apps get +5 nice.
Xorg and xfwm4 retain -5. The launchers (panel, dock, settings daemon and desktop)
return to 0 so their children do not inherit the compositor's elevated priority.
This is scheduling under contention, not a CPU cap: background work can still use
otherwise idle CPU. Existing deliberate positive nice values are preserved as
baselines; negative values other than the old inherited -5 are left alone.

## What was wrong

The previous user service wrote application cgroups directly. Its cpu controller
was absent below app.slice in the live session, so the advertised 400/50 CPU
weights were not in effect. More seriously, application scopes contained the main
Electron processes while their zygotes, renderers and GPU processes remained in
session-c2.scope. Weighting the main process could not prioritize those helpers.
The memory.low reservation also had zero protection in its ancestor hierarchy;
there was no demonstrated memory-protection benefit.

The previous desktop-nice list included launchers. Firefox, ChatGPT and their
ordinary helper threads consequently ran at -5 too. The intended separation
between desktop rendering and application work was weakened.

## Implementation and cost

`bin/focus-priority` replaces the old watcher, rather than adding another one.
One xprop connection blocks on `_NET_ACTIVE_WINDOW` and `_NET_CLIENT_LIST`.
Related window events are coalesced for 80 ms. The watcher maps this user's
window-owning PIDs to their real descendants and adjusts ordinary scheduler
threads, including renderers, even across cgroup boundaries. It makes no memory
protection claim. Unrecognized focus returns managed apps to their baselines.
Closed-window trees are restored. No application is killed, suspended or restarted.

Thread identities include start times. Writes re-check identity and ownership;
threads whose priority another scheduler changes are relinquished. New children
that inherit our background adjustment recover their parent's baseline when
focused. The original priorities are recorded in `/run/mintbook-focus-priority-1000/`
and restored on orderly stop; the next start also attempts crash recovery.
Recovery records retain both sides of a pending adjustment, so an interrupted
batch can restore threads whose writes landed and threads still at the old value.

The service runs as the desktop user, with CAP_SYS_NICE, from a root-owned copy
under `/usr/local/libexec`. This capability is necessary to raise priority again.
The old unprivileged implementation could not implement this policy reliably.
Its system unit follows the user's systemd manager lifetime. Python runs isolated
from user import paths; the helper only adjusts its own user's processes.

A first implementation scanned every task/stat and used about 541 ms CPU on this
busy desktop. Restricting the scan to managed app trees and caching unchanged
thread identities reduced the measured first/warm scan to 186/57 ms for 1,302
threads. Identity is still checked before every actual write. Those are individual
cost observations, not a multi-run latency guarantee. There is no timer polling.

## Scheduling experiment

Eight arms, in 0/5/5/0/0/5/5/0 order for background nice, with eight samples each.
Foreground nice stayed 0. Both disposable processes were pinned to the same
logical CPU and shared a cgroup; the background loop competed with a fixed
PBKDF2 operation. Existing desktop activity continued. No real apps were
reprioritized for this experiment.

| Background nice | Foreground median | p95 | Samples |
|---|---:|---:|---:|
| 0 | 329.15 ms | 415.98 ms | 32 |
| 5 | 206.40 ms | 256.81 ms | 32 |

Foreground median was 37.3% shorter in this contention proxy. The four arm
medians were 315–377 ms at equal priority and 204–219 ms with background +5.
This establishes the scheduling mechanism's benefit under contention, not a
37% browser speedup, input-to-photon measurement, or battery-life improvement.
It spends background throughput to finish foreground work sooner.
Raw samples: [priority experiment](measurements/2026-09-09-priority.json).

## Install and undo

`pkexec bin/priority-install` creates a Timeshift snapshot on first install,
backs up the replaced system files, retires the old user service, installs the
root-owned helper, and starts `mintbook-focus-priority@1000.service`. The desktop
priority timer retains its existing schedule. Reruns retain the original backup.
`bin/focus-priority --check` is read-only and reports live app/thread priorities.
`--no-snapshot` uses the specific file backups only, when Timeshift is declined.

On September 10 the user stopped snapshot creation. Its process group was
terminated and its incomplete snapshot removed; the existing September 9 snapshot
was retained. Installation then completed with `--no-snapshot`. The old user
unit is disabled and removed from the repository. The new system unit is enabled.

`pkexec bin/priority-install --revert` stops the new helper, restores its thread
priorities and the backed-up desktop-nice files. The known-ineffective old user
focus service stays disabled; it is not a supported installation path anymore.

Policy regression tests cover helpers, nested windows, newly inherited thread
priorities, PID reuse, external priority changes, window closure and deliberate
audio priorities, plus undo across a partially applied batch.

## Live verification — September 10

The installed helper followed the user's focus changes between ChatGPT and Claude.
The foreground application's ordinary threads read 0 and the background trees
read 5; deliberate nice-19 threads remained at 19. Xorg/xfwm4 read -5 and all four
launchers read 0. The state included 682 managed threads. With focus unchanged
for 12.02 seconds, systemd's cumulative CPU accounting did not increase at all;
memory stayed about 11.4 MiB and restart count stayed zero.
[Live observations](measurements/2026-09-10-priority-live.json).

This verifies effective priorities and idle cost. It does not measure browser
page completion, input-to-photon latency, or throughput of whole app trees in
different scheduler cgroups. Threads born after a focus event inherit their
parent's priority; other new threads are discovered on the next window event.
