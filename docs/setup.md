# Install and update the desktop

The supported starting point is **Linux Mint 22.3, XFCE, X11**, with a normal
user account logged into its desktop. The repository defines the desktop in
[`config/desktop.json`](../config/desktop.json). No configured source account,
exported profile or copy of someone else's home directory is needed.

## First installation

From a terminal in the account that should get the GUI:

```bash
git clone https://github.com/garfbargle/mintbook.git
cd mintbook
bin/setup --install-deps
```

The flag permits setup to ask sudo for missing distribution packages; APT
shows what it will install. The desktop configuration and downloaded themes
are installed as the logged-in user. Do not run setup itself with sudo.
`bin/setup --check` reports prerequisites without changing anything.

Setup installs the theme, icons, dock, top bar, Control Center, Overview,
shortcuts and daily conveniences. It uses the existing feature installers
and `desktop-install`'s versioned activation, rather than maintaining a second
copy of those features. The panel layout and Mintbook shortcuts are managed
by the recipe and reapplied on updates.

The first run establishes the repository appearance defaults. Existing DPI is
retained unless explicitly supplied; an account without a usable DPI uses 96.
For the reference MacBook's Retina screen, supply 168:

```bash
bin/setup --install-deps --dpi 168
```

Night Light is optional. To configure it for a **new** account, supply that
user's coordinates, for example London:

```bash
bin/setup --location 51.5 -0.12
```

An existing `~/.config/redshift.conf` is preserved. Edit its `[manual]` section
to change location later; do not repeat `--location` once it exists. No
geolocation service or reference-machine coordinates are enabled by default.
Log out and back in after the first installation to exercise the dock, panel
and configured Night Light autostart in the new session.

## Updates and drift

In the checkout, run:

```bash
git pull --ff-only
bin/setup
```

Run this separately in each account you want to update. Pulling the repo
alone does not update an installed release or another account. There is no
automatic checkout of new code at login.

The same recipe runs for both installation and updates. Runtime code is built
from the checkout into a self-contained release, so it can continue running
if the checkout is moved. Each account owns its release links, state and undo
backup. The package list, exact external theme revisions and installer order
live in the repository, not in a snapshot of an operator's desktop.

Appearance, wallpaper and dock defaults update when the current value still
matches what setup last applied. Subsequent user changes to those defaults
are retained. `--reset-defaults` explicitly reapplies the repository defaults.
Panel structure and Mintbook keybindings remain managed; save custom panel
layouts before reapplying setup.

WhiteSur is downloaded from the pinned upstream commits in the recipe and
built into `~/.themes` and `~/.icons`. Thousands of icon files are ordinary
theme assets, not user profiles. Theme installation is skipped when the pin,
arguments and checked-in patches still match and the output exists. Changing
any of those inputs triggers a rebuild. Mintbook's patch suppresses WhiteSur's
session-restart hook; the release manager owns the panel lifecycle.

When developing a feature, keep its installer current. Add a newly enabled
feature to the recipe's installer list, then exercise a fresh setup and a
rerun. Runtime code changes enter the next release through the same setup
command; no export from a maintainer's account is involved.

## Verify and undo

```bash
bin/desktop-install --status
bin/doctor
```

Check the visible panel, dock, Control Center, Overview and shortcuts inside
the target session. Automated tests cover native XFCE property types and
arrays on private D-Bus, changed repository defaults, preserving a user's font
choice, theme pinning and recipe composition. Full first-login visual
verification in Natalia's account is still pending; setup has not been
applied to that account yet.

Before applying the recipe, setup saves the relevant GUI files, typed XFCE
settings, dock preferences and release links under
`~/.local/state/mintbook/setup-run-*`. The first backup is retained across
reruns. An installation/activation failure restores the per-run backup.

From the checkout, `bin/setup --revert` restores the GUI settings from before
the first setup. `bin/setup --recover` restores a run interrupted before it
finished. Downloaded theme files and installed packages remain available;
they are not automatically uninstalled. Existing `desktop-install --rollback`
continues to select the prior runtime release.

## Scope

Setup configures a user's desktop and its daily conveniences. It does not
provision firmware, boot loaders, kernel patches, hibernation UUIDs, system
hardware policies or the LightDM greeter. Those need the relevant hardware
and system guides and the README's Timeshift snapshot. The system's hardware
must already work before configuring its GUI. Other desktop environments and
non-Mint distributions are not covered by this recipe.

Mintdrop's protocol code is available in the runtime, but its shared listening
socket, advertisement and device identity remain opt-in through its dedicated
installer. Port 8771 can have only one listening account on a machine.

### Distribution tray applets

Setup writes per-user `Hidden=true` autostart overrides for `nm-applet.desktop`
and `mintreport.desktop`. Mintbook's Wi-Fi control and System health menu take
those tray seats. NetworkManager itself keeps running, and System Reports
remains available as an application. Undo restores the original autostart
entries. Other accounts retain their own settings.

Applications installed under `/usr/share/applications` are normally visible to
all users. Applications installed under one user's `~/.local` are available
only to that account. A per-user Relay installation must be installed for each
account separately; desktop setup does not copy another user's app data or
sign-ins.
