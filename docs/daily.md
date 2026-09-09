# Daily conveniences — 2026-09-07

`bin/daily-install` enables this set in the current desktop session. It snapshots
replaced files, the three window shortcuts and lid actions before changing them, prints an
undo command, and does not restart the panel. Reopen menus to see the changes.
The installed files link to this checkout, which must remain at its current path.
`bin/daily-install --revert` restores the prior files, shortcuts, lid actions and health timer;
backup files are retained in `~/.local/state/mintbook/daily-before-*`.

## Overview actions

Cmd+Space combines rofi's application mode with a curated script mode. Search
for `dark`, `Bluetooth`, `battery history`, `health`, `updates`, `keep awake` or
`sleep check`.
The app grid's first-keystroke handoff seeds the same combined search.

`bin/spotlight-actions` supplies Overview's labels, keywords and fixed IDs. Selection launches
only the corresponding fixed argv list, detached from rofi's pipes. Custom text
never becomes a command. Unavailable backends do not appear. Existing application
search remains available if the actions helper is missing.

**Arm a sleep check** starts one transient watcher and then returns. It never
suspends the machine. **Show last sleep result** puts the completed recovery and
battery result in a notification. Details and terminal commands are in
[input.md](input.md#the-sleep-black-box).

Closing the lid suspends on both battery and external power. This prevents a
plugged-in laptop from spending a closed-lid night awake and hot. Xfce does not
reconsider a lid that was already closed when the charger is later unplugged.

## Keep Awake

The System tray menu offers Off, 30 minutes, one hour and two hours in one
compact row; Overview offers the same durations. Remaining minutes appear next
to the row. A transient user systemd service holds both the power manager's and
screensaver's D-Bus inhibitors until expiry. Stopping the service releases them;
process exit releases the D-Bus ownership too. Nothing rewrites power settings.
Normal explicit lock/suspend actions remain the user's choice. This feature
pauses automatic screen locking while active; it is intended for presentations.

The state is in the user runtime directory, uses monotonic time, and verifies
process start identity to reject stale PIDs. There is no permanent awake daemon.
`keep-awake off` restores normal behavior immediately.

## Screenshots and windows

Screenshot shortcuts keep their existing save behavior and flash. Afterward a
notification offers **Copy** (an actual PNG image on the clipboard) and **Open**.
No xclip package is needed. GTK offers the image to the clipboard manager; without
one, its owner stays for up to ten minutes or until another copy replaces it.
Notification failure cannot undo the saved screenshot. Filenames include
nanoseconds to avoid collisions between quick captures.

Cmd+Left and Cmd+Right place the active window in half of its monitor's work area.
Cmd+Down restores the original geometry, including a previously maximized state.
Switching sides retains that original geometry. Fullscreen and desktop/dock
windows are left alone. Restored geometry is clamped to the current monitor if a
monitor has gone away. Apps' own minimum-size constraints can prevent exact halves.

## Keyboard menus

Control Center: Tab and Shift+Tab move between controls, including a toggle's
separate detail chevron. Enter/Space activates; arrows change options and sliders;
Home/End set sliders to 0/100. Dropdowns use Up/Down and Enter. Escape first closes
a dropdown, then the panel. A blue outline marks the keyboard target.

Wi-Fi, Bluetooth, battery and updates use the same Tab/arrows/Enter pattern.
Page Up/Down scroll the focused device/network/update list. Wi-Fi's password input
keeps its existing typing, Enter-to-join and Escape-to-cancel behavior. Item identity
is checked again before keyboard activation, so a refresh cannot silently change
the selected device. Keyboard navigation does not make the custom Cairo controls
fully screen-reader accessible; that would need a separate accessibility pass.

These override-redirect windows must grab the keyboard as well as the pointer.
Bluetooth releases the grab for pairing dialogs; updates releases it for
transactions/authentication. Control Center serializes writes per tile and
coalesces pending changes, so slow replies cannot reorder rapid key presses.

## System Health

[`bin/mintbook-health`](../bin/mintbook-health) is the desktop view of
[`bin/doctor`](../bin/doctor) — the System tray menu's Doctor detail, and
**Check system health** in Overview. It is a reader: it runs `doctor --tsv`,
caches the answer in `~/.cache/mintbook/health.json` for the tile, and draws it.
No check and no repair lives here.

The window opens on the cached answer and re-checks behind it. `doctor --tsv`
takes about 3.5 s on this machine, and a window that shows nothing for that long
is one you stop opening; the summary card says *checking now* while it runs, and
the list is replaced when the answer lands.

It is cairo on the popup glass, like the Control Center and the battery history
window — same palette source, same `appearance.applied` light/dark, same
`bin/palette-generate --check` drift guard. What it draws:

- A **summary card**: one sentence for the machine's state, the counts under it,
  and the kernel the answer belongs to. Green tick, amber triangle, red circle —
  shape as well as colour, so the state does not depend on seeing hue.
- **A warning is not a fault**, and nothing in the card treats it as one.
  `doctor` exits 0 on a run with nothing but warnings in it, and several of
  them — `cpu mitigations`, `thermald`, the trimmable services — are recorded
  policy rather than a problem. So the card is green and says *"Everything
  checks out"* unless something actually failed, the notes are a word at the
  end of the count line (*"83 passed · 2 notes"*), and only a failure gets the
  headline: *"1 check needs attention"*.
- **Errors / Notes / All**, showing only the filters that have findings. The
  System menu opens the exact count clicked. An ordinary open starts with
  errors only when there is a failure — opening on the notes would
  make them the whole window on a machine whose card says it is fine. With
  nothing to filter the segment is not drawn at all.
- Findings **grouped under doctor's own section headings**. `doctor --tsv` prints
  those headings now; grouping the desktop view by guessing at label text would
  be a second, quietly diverging opinion about what belongs together.
- A passing check whose detail fits gets **one line**, label left and detail
  right. Two lines are for findings you have to read.
- A finding whose detail names a repair command carries that command as a **chip**;
  clicking it copies it. The commands are read out of doctor's own detail text
  rather than kept in a table here, so there is nothing to drift. The exception
  is the handful of findings that name no command — `updates genmon rc` and
  `failed units` — which map to one in `REMEDY`.
- Clicking a finding copies `status label — detail`; **Copy report** (or `C`)
  copies the whole run. That replaces the old selectable labels, which is what
  anyone opening this window in order to file an issue was using them for.

`Esc`/`Q` close, `R` re-checks, `1`/`2` switch the filter, arrows and Page
Up/Down scroll. The list scrolls with its own overlay bar rather than a
`Gtk.ScrolledWindow`, for the same reason nothing else here is a themed widget.

The user timer checks two minutes after startup, then every six hours, but runs
`doctor` only when the running kernel differs from the last completed check.
Notifications report newly failing check names; unchanged results remain quiet.
A manual Check again is always available, including after repairs on the same kernel.

The findings in the screenshots are this machine's real ones and predate the
window: the missing `genmon-20.rc`, the CPU mitigation note and the thermal
notes are existing policy and measurement results, not anything this view does.

## Validation

Regression tests cover fixed action dispatch, ignored custom input, health record
parsing, the section each finding is filed under, the repair command read out of
a finding's detail, keyboard focus/slider bounds, device-list refreshes and
per-tile write ordering. A live two-second inhibitor test verified acquisition, expiry and clean
release. Window tests verified exact restoration of normal and maximized windows.
A separate test selection verified PNG clipboard transfer and ownership cleanup
without changing the user clipboard. The installer undo was executed, all backed-up
files and shortcuts compared, and the improvements reinstalled. Each changed popup was opened on the actual display for layout and
keyboard checks. Sleep itself was not changed or triggered: the user reports it
has worked over the last few days; see input.md for the remaining measurement gap.
