# Setting up another account or machine

Mintbook is a reference configuration for Linux Mint 22.3 with XFCE on X11,
measured on a MacBook8,1. It is not a complete distribution or a one-command
fresh desktop installer. Other hardware and desktop environments have not
been validated. `desktop-install` migrates an already configured desktop;
it does not create the reference panel layout, install themes or provision
all feature dependencies on a fresh account.

Clone the repository into the target user's home, then run these read-only
checks from that user's XFCE terminal, without sudo:

```bash
git clone https://github.com/garfbargle/mintbook.git
cd mintbook
bin/setup-check
```

The checker reports missing session tools, Python GTK bindings, the user
service manager and `~/.local/bin` in PATH. It does not install packages or
change settings. Its passing result covers these prerequisites, not every
optional feature or hardware device. Keep this checkout available while
using feature installers that link to it.

Follow [desktop.md](desktop.md) for the theme dependencies and panel layout,
[display.md](display.md) for scaling, and each feature's documentation for its
installer, dependencies and undo. Install only the features you want. Desktop
installers run as the target user; use sudo only for documented system steps.
Avoid copying another account's `.config`, state, backups or release manifests:
release targets and undo snapshots contain absolute paths for their owner.
The same installed release directory must not be shared between accounts.

## Preferences that belong to each user

Launchers and genmon commands are resolved by their feature installers.
The checked-in genmon and desktop files use command names as templates;
do not copy them as a substitute for running those installers. Mintdrop's
Plank launcher is generated with the target account's desktop-file URI,
including escaping spaces in the path. `bin/mintdrop-install --no-advert`
can install its user files without the system advertisement step; the usual
`--revert` restores the original launcher. Port 8771 is shared by the machine,
so only one account's Mintdrop socket can listen on it at a time.

Night Light needs the user's own location, not the reference machine's:

```bash
# Example coordinates for London; substitute your latitude and longitude.
bin/night-install --location 51.5 -0.12
```

The installer validates coordinates before changing the panel. With an existing
`~/.config/redshift.conf`, run `bin/night-install` without `--location`:
it keeps the entire file, including location and temperature preferences.
To change location later, edit its `[manual]` section. No geolocation service
is enabled. `config/redshift.conf` contains placeholders and must be rendered
by the installer. Manual Night Light process cleanup only inspects the current
user's Redshift processes.

## Verify and recover

After configuring the desired features, use `bin/desktop-install` to migrate
that account's installed components into versioned releases. Check with
`bin/desktop-install --status` and `bin/doctor`. Test launchers, shortcuts and
Night Light inside that user's session. This work has automated coverage for
two different home paths (including spaces), location validation and preserving
existing preferences; a complete fresh-account desktop has not been exercised.

`bin/desktop-install --rollback` selects the previous release;
`--revert` selects the original migration baseline. Individual feature undo
commands are documented alongside their installers. Night Light setup leaves
an existing Redshift configuration untouched; if it created a new one, remove
that file manually when undoing the feature. Take the README's Timeshift
snapshot before system or hardware changes. Boot settings, hibernation UUIDs,
firmware, device paths and performance/security choices must be reviewed for
the actual machine; do not apply the reference hardware configuration wholesale.
