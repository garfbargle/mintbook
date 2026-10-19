# Working on Mintbook

This is a working MacBook desktop, and the repo also contains its hardware fixes.
Keep each change bounded and retain the measured decisions in the relevant doc.

1. Read the relevant `docs/*.md` and the script's comments before editing. The
   docs distinguish measured results, user reports and untested ideas.
2. Prefer existing `bin/` backends. A Control Center tile implements `read` and
   `set <value>`; reads should be cheap and return actual system state. Overview
   uses fixed action IDs and argv lists, never executes the user's search text.
3. No ongoing work for a closed popup. Keep timers coarse; measure idle CPU and
   launch latency before adding polling or a resident process.
4. Use `bin/palette-generate` after changing `config/theme/mintbook-glass.ini`.
   `bin/palette-generate --check` verifies the embedded popup colors. Generation
   happens while developing; a missing config must never prevent a popup opening.
5. Run Python syntax checks, `bash -n` for changed shell scripts, and
   `python3 -m unittest discover -s tests -v` when changing action dispatch,
   keyboard handling, health parsing or setting writes. Exercise changed UI in
   both appearances at this machine's actual DPI. Do not install updates,
   disconnect devices or suspend the machine just to smoke-test a menu.
6. Install with the feature's installer. `bin/daily-install` installs the daily
   conveniences and their shared keyboard module;
   reruns retain the original undo snapshot. Once `bin/desktop-install` has
   migrated the desktop, feature installers use its maintenance and release
   transaction. Install code through that command; keep preferences outside
   release directories. `--rollback` restores the previous desktop release.
   Avoid changing files directly in `~/.local/bin`: they are managed links.
7. `config/desktop.json` is the install/update recipe: package prerequisites,
   pinned external themes, initial GUI defaults and ordered feature installers.
   Keep a feature's installer current and add newly enabled features to this
   recipe. Do not export a maintainer account to define the product. Test fresh
   setup and reruns, including custom preferences, when changing setup behavior.
8. Record what changed, what was tested, limits and undo steps in the feature doc.
   Keep historical measurements labelled with their original date.

Hardware traps: OpenCore chooses boots; GRUB does not. Preserve the applespi DMA
blacklist/resume hook and the Bluetooth DSDT override. Use the EQ audio sink,
never the raw speaker sink. Keep xfwm4's panel strut and 52px margin aligned.
Do not add blur/picom or repeat tuning advice already disproven in the docs.

Before invasive system changes, follow the Timeshift instruction in README.
User-level daily conveniences have their own file/shortcut backup and need no root.
