# Daily conveniences — 2026-09-07

`bin/daily-install` enables this set in the current desktop session. It snapshots
replaced files, the three window shortcuts and lid actions before changing them, prints an
undo command, and does not restart the panel. Reopen menus to see the changes.
The installed files link to this checkout, which must remain at its current path.
`bin/daily-install --revert` restores the prior files, shortcuts, lid actions and health timer;
backup files are retained in `~/.local/state/mintbook/daily-before-*`.

## Spotlight actions

Cmd+Space combines rofi's application mode with a curated script mode. Search
for `dark`, `Bluetooth`, `battery history`, `health`, `updates`, `keep awake` or
`sleep check`.
The app grid's first-keystroke handoff seeds the same combined search.

`bin/spotlight-actions` supplies labels, keywords and fixed IDs. Selection launches
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

The Control Center switch starts a 30-minute timer or stops the active one.
Spotlight offers 30 minutes, one hour and two hours. Remaining minutes appear in
the tile. A transient user systemd service holds both the power manager's and
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

The panel runs `doctor --tsv` asynchronously and shows failures and notes first,
with passed checks collapsed. Diagnostic details can be selected/copied.
The Control Center tile uses cached results; opening the view rechecks.
The user timer checks two minutes after startup, then every six hours, but runs
`doctor` only when the running kernel differs from the last completed check.
Notifications report newly failing check names; unchanged results remain quiet.
A manual Check again is always available, including after repairs on the same kernel.

A missing `genmon-20.rc` update-indicator configuration was reported by the first
check on this machine. This predates these changes; the health view exposes the
existing doctor result. CPU mitigation and thermal notes are also existing policy
and measurement findings, not changes made by this feature.

## Validation

Regression tests cover fixed action dispatch, ignored custom input, health record
parsing, keyboard focus/slider bounds, device-list refreshes and per-tile write
ordering. A live two-second inhibitor test verified acquisition, expiry and clean
release. Window tests verified exact restoration of normal and maximized windows.
A separate test selection verified PNG clipboard transfer and ownership cleanup
without changing the user clipboard. The installer undo was executed, all backed-up
files and shortcuts compared, and the improvements reinstalled. Each changed popup was opened on the actual display for layout and
keyboard checks. Sleep itself was not changed or triggered: the user reports it
has worked over the last few days; see input.md for the remaining measurement gap.
