# Software updates — the icon that is only there when it needs to be

<p align="center">
  <img src="images/updates.jpg" alt="the Software Update popup" width="620">
</p>

Linux Mint ships a very good Update Manager. It is a window, and it lives in
the systray as an icon that is always present, always the same, and says what
it has to say in a tooltip. macOS puts the same information in two places
instead: a badge that appears when there is something to do, and a pane you
open to do it.

This is that split.

```
bin/updates-install            # plugin-20 on the bar, and the timer
bin/updates-install --revert   # both off; nothing installed is removed
```

Mint's Update Manager is untouched by all of this and is still one click away
in the popup's footer — it is where the things a popup should not try to be
live: update history, the kernel list, sources, automation, the blacklist.

---

## The four pieces

| | what it is | what it costs |
|---|---|---|
| [`bin/updates-check`](../bin/updates-check) | reads the APT cache, writes two files | **2.5 s of CPU** |
| [`bin/panel-updates`](../bin/panel-updates) | the bar icon; reads one of those files | **6 ms**, every 5 min |
| [`bin/updates-menu`](../bin/updates-menu) | the glass popup | 300 ms to open |
| `mintbook-updates-check.timer` | runs the check 5 min after login, then every 6 h | |

The whole design is that ratio. Working out what apt has waiting means loading
the package cache and running a dist-upgrade resolution, which is two and a
half seconds of a fanless Core M — about four hundred times what a bar
indicator can spend. So the indicator never asks. It reads

```
~/.cache/mintbook/updates.state     count = 4, security = 1, size = 82190144, …
~/.cache/mintbook/updates.json      the list, for the popup
```

and draws a conclusion. A timer keeps those two honest, the popup re-runs the
check every time it opens, and `bin/doctor` is what tells you if the timer has
stopped — see [Staleness](#staleness).

`updates.state` is `key = value` lines because both of its readers are bash:
the genmon script and the Control Center tile. It is the same format the
Control Center plugins already speak. Both files are written with a rename, so
a popup reading while the check writes never sees half a file.

### It does not decide what an update is

`bin/updates-check` imports `checkAPT.APTCheck` out of
`/usr/lib/linuxmint/mintUpdate` — the same class behind `mintupdate-cli list`
and the Update Manager window. Packages are grouped into one update, named,
typed (`security` / `kernel` / `package`), described and aliased exactly the
way the Update Manager does it, and `/etc/mintupdate.blacklist` is honoured, so
an update ignored there is ignored here too.

Writing that against python-apt directly would have been a second opinion about
what an update is, and two opinions on one bar is one too many.

---

## The icon is not always there

When nothing is waiting, `bin/panel-updates` prints no image and the indicator
disappears. That is the same rule the Control Center plugins follow — *say
nothing rather than show a dead switch* — and it is why the bar is quiet
almost all of the time.

It sits **to the left of the CPU sparkline**, and that position is the whole
reason it can afford to come and go. The bar is packed against the right edge,
so an item added at the left end of the group grows the group leftward and
nothing already on it moves. Anywhere further right, every appearance and
disappearance of this icon would have shuffled the clock.

Two states:

| | when |
|---|---|
| the plain arrow | ordinary package updates |
| the arrow with a dot beside it | there is a **security** or **kernel** update in there |

Nothing shouts about a translation package. A bar that raises its voice for
everything is a bar you stop reading.

The tooltip carries the rest: the count, the total download, the breakdown and
when the answer was last checked.

### So where is the door when the icon is gone?

The Control Center, after Power: an **Updates** tile that is always present,
reads the same state file, and opens the popup from its `›`. That tile is
`control-center/plugins/70-updates`, twelve lines of bash, and it is the reason
hiding the bar icon is not a trap.

---

## What the popup can do

- **Update All** — the blue one. Everything on the list.
- **Update**, per row — one update, on its own. Security first, then kernel,
  then alphabetical; the order comes out of `updates-check`, so the popup and
  the file on disk cannot drift.
- **The circular arrow, top right** — refresh the package lists and check again.
- **Update Manager…** — Mint's window, for everything else.

Six rows fit; a longer list scrolls under the pointer and says `1–6 of 9`.

### The privileged half is aptkit, not us

Nothing in mintbook runs as root to do this. Installing goes through
**aptkit** — the same backend the Update Manager uses, the same
`org.aptkit.install-or-remove-packages` polkit action, the same daemon doing
the dpkg run. The popup is a client of it: it gets the status, the progress and
the failure back over D-Bus and draws them in its own row.

Two consequences worth knowing:

- **The transaction outlives the popup.** It runs in aptkit's daemon. Killing
  `updates-menu` mid-install does not stop the install.
- **Refreshing the lists costs no password.** `org.aptkit.update-cache` is
  `allow_active=yes`. Installing is `auth_admin_keep`, so that one asks — once,
  and then not again for a few minutes.

### It lets go of the seat to let you type

The popup holds a pointer grab, which is how a click outside dismisses it. The
polkit agent needs the **keyboard** to ask for a password, and an override
redirect window holding the seat leaves that dialog unable to take a single
keystroke.

So the grab is dropped the moment a transaction starts and taken again when it
ends. While an install runs, clicking outside does nothing and the popup stays
where it is — which is also where the progress bar is.

### What it asks before it installs

Before aptkit is called at all, python-apt resolves the request against the
same cache: mark the packages, take `cache.get_changes()`, and see what else
that drags in. If anything would be **newly installed** or **removed**, the
popup says so and waits, with the removals in red.

That resolution is a plain read of files this user can already read, and it
happens *before* the password prompt rather than after it — which is the point.
Being told what a click entails is worth less once you have already typed your
password for it.

It is also why `simulate()` is never called on the transaction: apt's resolver
has already answered, and asking a second resolver only buys a second answer to
compare against.

### What it says when it does not work

| | shown as |
|---|---|
| you dismissed the password prompt | *Not authorised*, in plain ink |
| you pressed Cancel | *Cancelled*, in plain ink |
| dpkg failed | the first line of aptkit's error, red |
| a repository failed to refresh | amber, and the check still runs |

A dismissed password prompt arrives from aptkit as
`org.freedesktop.PolicyKit.Error.NotAuthorized`. Putting that string on screen
under a red dot calls the user's own "no" a fault, so `humanise()` in
`bin/updates-menu` is the one place raw D-Bus errors are turned into a line.

A kernel update that installs adds `· restart to finish the kernel` to the
success line, in amber.

---

## Staleness

Every check above can be green while the answer on the bar is a week old, and
a stale *"nothing waiting"* is precisely the lie this indicator exists to
avoid — the same failure the Wi-Fi icon had when it drew three full bars over
a dead uplink.

The bar itself does not police this, on purpose: an icon that appears to nag
about its own timer is worse than the problem. `bin/doctor` does:

```
  ok    updates state    1 waiting (0 security), checked 1h ago
```

and it warns past 18 hours, which is three missed runs of a 6-hour timer. The
popup's header carries the same fact in words — *checked 2 hours ago* — every
time you open it.

---

## What this does not do

- **Flatpaks.** The Update Manager counts them; this does not. Two flatpak apps
  are installed on this machine and neither has ever needed an update badge, so
  the cost of a second backend with its own refs, its own resolution and its own
  progress model was not worth paying yet. `flatpak update` and the Update
  Manager both still work. **The count in the popup is an apt count, and the
  doc says so rather than the popup implying otherwise.**
- **Cinnamon spices.** Not applicable — this is XFCE.
- **Automatic installs.** Nothing here installs anything you did not press a
  button for. Mint's `mintupdate-automation` is untouched and, if you want it,
  it is behind the Update Manager's own preferences.
- **A confirmation for the ordinary case.** If a click pulls in nothing new and
  removes nothing, it goes straight to the password prompt. The prompt *is* the
  confirmation.

---

## Cost, measured

`bin/panel-updates`, 20 runs, on 2026-09-07:

```
20 invocations, 0.128 s total → 6.4 ms each
```

At the rc's 300 s period that is 0.002% of a core — the cheapest thing on the
bar by a factor of ten, and it stays that way because it never grows a second
job. Compare `panel-cpu` at 46.7 ms every 2 s (2.34%) and `panel-wifi` at
29.7 ms every 5 s (0.59%); see [control-center.md](control-center.md).

`bin/updates-check`, the expensive half, on a busy machine: **2.5–3.0 s**
across the runs measured here, of which nearly all is `apt.Cache()` and the
dist-upgrade resolution. Four runs a day is about 11 seconds of CPU a day.

Opening the popup: the cached list is drawn immediately and the re-check runs
behind it, the same way `bin/wifi-menu` shows the cached scan and rescans
behind it. The check is spawned on the first line of the file, *before*
`import gi`, so the ~220 ms GTK import happens inside it for free.

---

## Undo

```bash
bin/updates-install --revert
```

Takes plugin-20 off the bar, disables the timer, and removes the three scripts,
the Control Center tile and the icons. `plugin-20` stays registered but unused;
the cached list in `~/.cache/mintbook/updates.json` is left alone. Nothing that
was installed by apt is touched, and Mint's Update Manager was never modified
in the first place — `mintupdate` still opens the window it always did.

---

## Gotchas

- **`trans.run(error_handler=…)` alone raises.** aptkit's `MissingReplyHandlerException`
  says *"if you define an error_handler you must also define a reply_handler"* —
  and it comes out of `run()` rather than reaching the handler you did give it,
  so the first version failed silently before any transaction ever started. Both
  handlers or neither.
- **A finished transaction keeps emitting for a moment.** The refresh
  transaction's last `status-changed` landed in the header while an install was
  already preparing, so the popup said *"Loading software list"* over a progress
  bar for a package install. Every handler now ignores anything that is not the
  current transaction.
- **`pkill -f updates-menu` kills the shell that ran it.** `-f` matches full
  command lines, and the command line containing the pattern includes the one
  doing the matching. Cost two confusing exit-144s. The pidfile is there for
  exactly this; use it.
- **`progress` can be 101.** aptkit's way of saying it has no idea. The bar
  draws a sliding lozenge for anything over 100, because a progress bar frozen
  at 0 while dpkg works looks like a hang.
- **The refresh button surfaces a repository that has been broken for a while.**
  The first press on this machine came back amber: a third-party apt source
  whose signing key is not installed. apt goes on with every list it *did* get,
  which is why nothing had ever mentioned it. That is the check working, not
  the popup failing — but it does mean the amber line is a thing you will see
  and have to decide about rather than a rare event.
