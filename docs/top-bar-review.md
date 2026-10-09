# Top-bar and environment review — 2026-10-08

Reviewed `garfbargle/mintbook` against the installed Linux Mint 22.3 setup on
MacBook8,1, kernel 7.0.0-38-generic, Python 3.12.3 and the 168 DPI X11 desktop.
Changes were developed in an isolated task checkout; the original checkout and
its uncommitted brightness plugin were preserved.

## Findings and fixes

| Area | Observed problem | Result |
|---|---|---|
| Login helper | A valid picture filename could execute sed commands as root; dconf parsing used a shell | Literal config writes, isolated typed GSettings parsing, and copies read with the caller's permissions |
| Power helper | Group-writable runtime state could redirect a root write through a symlink | Private root-owned policy directory, atomic cap replacement, regular bounded no-follow request reads |
| Mintdrop | Predictable staging paths followed symlinks; concurrent receivers could overwrite a final file | Random exclusive staging and exclusive final publication for both protocols |
| Quick Share | Overlapping/out-of-order chunks could satisfy the byte counter with a truncated file | Require contiguous bounded offsets and verify final length before publication |
| Protocol dispatch | One short TCP read misclassified the handshake; silent peers held slots | Read the entire prefix with a deadline and replay it to the selected protocol |
| Popup ownership | Duplicate-launch races and stale PID files could signal unrelated processes | Process-lifetime file locks and pinned, validated process identities |
| Updates | Exported unattended-upgrade blacklist disagreed with Mint's live settings | Use APTCheck's live filter and Mint's system Flatpak worker; label additional user Flatpaks explicitly |
| Update freshness | Cache refresh was the only watched input; repeated checks competed | Watch dpkg, Flatpak and live preferences too; quiet interval, signature filter, shared collector lock |
| Update lifecycle | Escape/outside/window close discarded the observer or Flatpak worker | Hide while checking/installing; reopen the same progress; stop hidden animation and exit after completion |
| Control Center | Slow live reads could queue; dismissal could lose the latest slider value | One read per tile in flight; preserve/coalesce pending writes before exiting |
| Worker failures | A timeout could skip the completion callback and leave optimistic state or “Running” forever | Settle controls and reread actual state in failure paths |
| Bluetooth | Repeated BlueZ reads could block GTK for the full D-Bus timeout | A single background snapshot with main-thread delivery |
| Brightness | Untracked shell curve, suppression races and multiple gamma owners | Versioned shared controller, validated actual state and one systemd Redshift owner |
| Installation drift | Old doctor/revert helpers and brightness setup lived outside Git | Feature installers synchronized the desktop copies; doctor exposes remaining root-helper differences |

Regression reproductions use temporary files and fake backends: no exploit was
run against live root files. No packages were upgraded, devices disconnected,
or suspend/hibernate triggered as a smoke test.

## What remains running

The bar readers use cached state or existing system interfaces. Idle closed
popups exit. The update popup remains alive only while its check/transaction is
active; a dismissed Control Center waits only for pending writes. Bluetooth
scanning is stopped when its popup closes. The existing brightness watcher
remains one process and reads sysfs/state directly once a second.

| Menu | Backend / boundary |
|---|---|
| System | Cached health/updates, bounded background Doctor/Keep Awake actions; confirmation for session power actions |
| Control Center | Existing plugins, bounded worker pool and authoritative rereads |
| Updates | Mint APTCheck and aptkit; Mint's system Flatpak worker; user-scoped Flatpak transactions |
| Wi-Fi | NetworkManager/nmcli; scans and connection work stay outside GTK |
| Bluetooth | BlueZ; one snapshot at a time, scan lifetime tied to the popup |
| Battery | UPower plus the existing power request backend |
| CPU | Existing sampler/app-color cache; sampling only while the menu is open |

Mint 22.3's Update Manager queries system Flatpaks. This machine has user apps
and user runtimes, so a user-tagged row in the popup can legitimately be absent
from Mint's window. Runtime branches are displayed to distinguish similarly
named refs. A read-only resolved transaction confirmed that the three locale
rows were actual planned operations; the transaction was aborted before
installation/authentication.

Ordinary dismissal preserves update progress. Forced process termination,
a crash or logout still ends a user Flatpak worker; aptkit owns APT separately.
There is no claim of crash-proof transaction recovery. Some individual BlueZ
scan/action calls retain their bounded D-Bus timeout; this pass moves repeated
snapshot reads off GTK, not every possible hardware operation.

## Measured costs and verification

Measurements are single warm samples during this review, not controlled
benchmarks under identical background load:

- Existing brightness watcher: **215.954 ms CPU / 10 seconds** including child
  processes. New direct-file watcher: **4.033 ms / 10.012 seconds** (about 98%
  less idle CPU for this watcher).
- Control Center: **216 ms** to screen before; **203 ms light / 198 ms dark**
  afterward, with nine tiles.
- Update popup: **239 ms light / 189 ms dark** to screen. A cache younger than
  60 seconds avoids an unnecessary collector on reopen.
- **326 unit tests passed**, plus syntax checks, shell parsing, palette consistency and
  whitespace checks were run. Focused regressions cover staged-file races,
  fragmented handshakes, chunk bounds, literal privileged config values,
  popup ownership, active-job dismissal, pending writes and failed backends.
- Visual smoke checks use both appearances at the actual desktop DPI without
  changing the applied appearance. No install/update buttons were clicked.

The initial review found no failed system/user services, about 32 GB free root
space, working zram plus disk swap, and battery capacity about 83% of design.
CPU mitigations remain deliberately disabled; cumulative thermal throttling
exceeded 1% of uptime, and the last controlled sleep evidence is from September.
Those hardware/boot choices were not changed. Device checks from restricted
command environments can lack `/dev/snd` or `/dev/dri`; do not treat those
visibility warnings as proof of a hardware regression.

## Installation and undo

The update installer bounds panel shutdown and its initial collector, starts
the panel detached, and never kills a potentially active Mint Update Manager.

Desktop updates use the documented feature installers: `daily-install`,
`brightness-install`, `updates-install`, and `mintdrop-install --no-advert`.
Daily and brightness installers retain their file/shortcut/unit snapshots.
Brightness preferences and the base Redshift config are preserved. Redshift
uses CLI brightness/temperature overrides against the existing config path,
so AppArmor permissions need no change.

XFCE 4.18.3 grabs brightness keys even when its brightness handler is disabled.
The installer briefly stops Power Manager, rebinds the two shortcuts through
xfsettingsd, then starts Power Manager again. Existing shortcut settings load
before application autostart at normal login; a fresh login was not performed
as part of this review. Upstream behavior is visible in
[xfpm-button.c](https://raw.githubusercontent.com/xfce-mirror/xfce4-power-manager/xfce4-power-manager-4.18.3/src/xfpm-button.c).

The desktop was at the LightDM lock screen during the key smoke test. Logind
returned “Session is not in foreground, refusing.” The new helper correctly
reported failure and retained the prior state. Full brightness-key verification
requires the unlocked foreground session; no lock-screen bypass was attempted.

Root deployment requires administrator authentication:

```bash
sudo bin/safety-install
bin/input-boost-install
```

The first command creates a Timeshift snapshot, saves the previous root files
under `/var/lib/mintbook/safety-backups`, replaces only the login/power helpers
and power tmpfiles config, and reasserts the current profile. The second updates
the user Input Boost client/unit only after protected policy state exists.
Doctor checks installed helper revisions and policy-state ownership.

Undo the user policy client with `bin/input-boost-install --revert` first,
then use the exact `safety-install --revert BACKUP` printed by the root installer.
Other feature installers accept `--revert`; their original snapshots are kept.
Root fixes committed to Git do not protect installed old helpers until this
administrator step succeeds.
