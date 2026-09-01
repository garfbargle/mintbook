# Desktop — the macOS look

Making XFCE on this machine look and behave like macOS: the top bar, the dock,
Spotlight, the window manager and the panel indicators.

Scaling and DPI are **not** here — see [display.md](display.md).

---

## User preferences (stated explicitly)

- **No Apple logo anywhere.** The macOS look is wanted, the branding is not.
  Note WhiteSur's `start-here-symbolic` *is* an Apple logo despite the neutral name —
  the panel button uses Adwaita's `view-app-grid-symbolic` instead.
- **No blur.** Translucency only. Real blur (picom `dual_kawase`) was offered and
  declined on performance grounds. There is no picom; xfwm4's own compositor does the
  translucency at no extra process cost.
- **Keybindings: minimal.** Full Mac-style remapping (Toshy) was offered and declined.
  Only the Super key was freed and Cmd+Space bound. Copy/paste stays on Ctrl.
- **The top bar must stay thin.** 52px. A 64px bar was tested and rejected.

---

## What is installed

From the Mint repos:

```
plank rofi xdotool sassc libglib2.0-dev-bin libxml2-utils fonts-inter
xfce4-cpugraph-plugin xfce4-sensors-plugin xfce4-genmon-plugin
lm-sensors gnome-system-monitor btop
```

From GitHub (cloned to `~/src/`):

- `vinceliuice/WhiteSur-gtk-theme` → installed to `~/.themes` as
  `WhiteSur-Light`, `-Dark`, plus `-hdpi` / `-xhdpi` variants
- `vinceliuice/WhiteSur-icon-theme` → installed to `~/.icons` as `WhiteSur-light`

Install command used for the GTK theme (`-o normal` is the translucent variant —
this is what provides the "glass" look without a blur pass):

```bash
cd ~/src/WhiteSur-gtk-theme
TERM=xterm-256color ./install.sh -o normal -c light -c dark -a normal -t default -d ~/.themes
```

> `TERM` must be set or the installer dies silently. It calls `setterm`, which fails
> when `$TERM` is unset, and the script hides stderr in `/tmp/WhiteSur.lock/error_log.txt`
> and deletes that directory on exit. It exits 1 with no visible message.

`xfce4-sensors-plugin` is installed but **unused** — see Gotchas.

---

## Current configuration

### Top bar (xfce4-panel, `panel-1`)

| Setting | Value |
|---|---|
| `position` | `p=1;x=0;y=0` (top, full width) |
| `size` | 52 |
| `icon-size` | 36 |
| `background-style` | 1 (solid colour) |
| `background-rgba` | `0.13, 0.13, 0.14, 0.55` — dark translucent glass |

Plugin order (`plugin-ids`), left to right:

| id | plugin | notes |
|---|---|---|
| 1 | whiskermenu | `button-icon=view-app-grid-symbolic`, no title |
| 7 | separator | `expand=true` — pushes everything right |
| 8 | systray | "the rest" — currently just Claude's tray icon |
| 10 | xapp-status-plugin | "the rest" — empty now; kept so any future XApp icon has a home |
| 19 | genmon | CPU sparkline |
| 17 | genmon | CPU temperature |
| 20 | genmon | update manager |
| 18 | genmon | Wi-Fi |
| 12 | pulseaudio | volume |
| 11 | power-manager-plugin | battery |
| 13 | clock | ` %a %-d %b  %H:%M  `, Inter 11, `digital-layout=3` (time only) |

Right-to-left: **date/time, battery, volume, wifi, update manager, temperature, CPU,
then the rest.** This follows the macOS convention — the clock is furthest right with
the battery beside it, then volume, then Wi-Fi. Informational items (update, temp, CPU)
sit inboard of the system status group, and anything unrecognised accumulates
right-to-left from the far left of the group.

**Reordering panel items:** XFCE has no macOS-style hold-a-key-and-drag. The
equivalents are right-click any item → **Move** (then drag it along the bar), or
right-click → Panel → Panel Preferences → **Items** tab, which is a drag-to-reorder
list. Anything in `plugin-ids` can also just be reordered in xfconf, which is what
was done here.

### CPU sparkline (`plugin-19`, genmon)

Runs [`bin/panel-cpu`](../bin/panel-cpu), which renders an SVG sparkline to
`~/.cache/mintbook/cpu.svg` every 2s.

`xfce4-cpugraph-plugin` was used first and then **removed**. It draws hard vertical
edges with no way to soften them, and its tooltip is not controllable. The genmon
version gives:

- **Faded leading/trailing edges** via a `<linearGradient>` inside a `<mask>`, so the
  trace dissolves into the bar instead of ending abruptly. Verified in the rendered
  pixbuf: alpha ramps 0 → 209 → 8 across the width.
- **A tooltip listing the top 5 processes** by CPU. These are *interval* percentages
  computed from `/proc/<pid>/stat` deltas between runs — not `ps`'s since-process-start
  average, which is misleading for a live readout.
- **Click opens System Monitor.**

The tooltip is wrapped in `<span font_family="monospace">`. This is required, not
cosmetic: GTK tooltips render in a proportional font, so space-padded columns do not
line up without it.

State (previous jiffies + history + per-process times) lives in
`~/.cache/mintbook/cpu.state`, written via a temp file and `os.replace` so a
half-written file is never read.

> GTK tooltips are not interactive, so a *button* inside the hover is not possible —
> hence click-to-open. Task Manager remains on its existing **Ctrl+Shift+Esc** binding.

### Temperature (`plugin-17`, genmon)

genmon does **not** use xfconf — it reads `~/.config/xfce4/panel/genmon-17.rc`.
It runs [`bin/panel-temp`](../bin/panel-temp), which finds `coretemp` **by name** (hwmon
numbering is not stable across boots), prints the package temp, and colours it
white / amber at 80°C / red at 90°C. Tooltip adds SSD and PCH temps.

The label is **fixed-width**: the number is padded to three characters with U+2007
FIGURE SPACE (exactly one digit wide) and rendered with `font_features="tnum"`, so
the reading never changes width as the value moves between 2 and 3 digits. Verified
at a constant 38px for values from 7 to 100. Font is Inter 9.

The reading is **smoothed with an EMA** (alpha 0.35) held in
`~/.cache/mintbook/temp.state`. The raw sensor is instantaneous, and restarting the
panel is itself a CPU burst, so the reading used to jump high and then drift back over
~10s. State survives restarts, so the displayed value now eases rather than slamming.
The underlying heat was real — this smooths the presentation, it does not hide a
problem.

Its tooltip lists CPU / SSD / PCH / battery, right-justified inside a
`font_family="monospace"` span for the same reason as the CPU one.

### Update manager (`plugin-20`, genmon)

Runs [`bin/panel-update`](../bin/panel-update), icons from
[`icons/generate-update-icons.py`](../icons/generate-update-icons.py).

Reads **`~/.linuxmint/mintupdate/updates.json`** — mintupdate's own 90-byte cache — so
it never shells out to `mintupdate-cli`, which would hit apt metadata on every refresh.
Click opens Update Manager. Polls every 30s.

mintupdate's built-in tray icon is a 1px-thick ring that read far thinner than its
neighbours, and being an XApp icon it was stuck at 20px. It is now hidden with
`gsettings set com.linuxmint.updates hide-systray true`, and mintUpdate still runs in
the background doing its normal update checks.

> These icons use **strokes**, unlike the symbolic ones under `~/.icons`. That is safe
> here because genmon shows them via `<img>` with no GTK recolouring — the fill-only
> recolouring rule does not apply.

### Wi-Fi indicator (`plugin-18`, genmon)

Runs [`bin/panel-wifi`](../bin/panel-wifi), which reads link quality from
`/proc/net/wireless`, checks `/sys/class/net/<if>/carrier` for association, and
emits an `<img>` pointing at a pre-rendered SVG.

**This exists to escape the 20px xapp cap.** genmon renders `<img>` at the SVG's own
declared size, so these icons are 30px and match the speaker and battery. They are
generated by [`icons/generate-wifi-genmon.py`](../icons/generate-wifi-genmon.py) into
`~/.local/share/mintbook/wifi/`.

These are **not** symbolic icons — genmon shows them as plain images, so GTK does no
recolouring and the fill is hardcoded `#ffffff` for the dark bar. If the bar is ever
made light, re-run the generator with `COLOR` changed.

**nm-applet is disabled** (`~/.config/autostart/nm-applet.desktop` with `Hidden=true`)
so it stops claiming an XApp slot. NetworkManager itself is untouched and connections
work normally — verified `connected:full` with working DNS after the change.

> Trade-off: nm-applet was also NetworkManager's **secret agent**. Joining a *new*
> password-protected network no longer gives you a popup prompt. Use
> `nm-connection-editor` (which the indicator opens on click) or
> `nmcli device wifi connect <ssid> --ask`. To undo this entirely: delete that
> autostart file and run `nm-applet &`.

### Dock (Plank)

Launchers live in **`~/.config/plank/dock1/launchers/`** — *not* in
`~/.local/share/plank/`, which is where the themes go. The ordered list is
authoritative in dconf under `dock-items`; adding files alone does nothing.

```
theme=WhiteSur   position=bottom   icon-size=80   zoom-enabled=true
zoom-percent=150   hide-mode=intelligent   auto-pinning=false
```

Theme copied from `~/.themes/WhiteSur-Light/plank/dock.theme` to
`~/.local/share/plank/themes/WhiteSur/dock.theme`.

### Clock padding

The clock is the last item on the bar, so its text ran into the screen edge. The
`digital-time-format` carries a **leading space and two trailing spaces** — panel items
have no margin of their own and the clock plugin exposes no padding setting. This
yields 16px of trailing gap. If the format string is ever edited, keep those spaces.

### Window manager (xfwm4)

```
theme=WhiteSur-Light-hdpi        # hdpi variant for the Retina panel
button_layout=CHM|               # close/min/max on the LEFT, Mac order
title_alignment=center
margin_top=52                    # see Gotchas - this is what reserves the top bar
show_dock_shadow=false           # see Gotchas
```

### Spotlight (rofi)

`Cmd+Space` runs [`bin/spotlight`](../bin/spotlight), which toggles
`rofi -show drun` with [`config/rofi/spotlight.rasi`](../config/rofi/spotlight.rasi):
centred, 46% wide, 14% from the top, translucent dark, rounded 16px, fuzzy matching.

### Keyboard

```
/commands/custom/Super_L        = /bin/true              # frees the Super key
/commands/custom/<Super>space   = ~/.local/bin/spotlight
```

Copy/paste is deliberately unchanged: **Ctrl+C / Ctrl+V** everywhere,
**Ctrl+Shift+C / Ctrl+Shift+V** in the terminal.

---

## Gotchas — things that cost real time

**The panel sets no struts, and never did.** `_NET_WM_STRUT_PARTIAL` is absent on
every window on this system, and `_NET_WORKAREA` is full-screen. Maximized windows
therefore render *under* the panel. This was always true; it was simply invisible when
the panel was at the bottom. The fix is xfwm4's workspace margin
(`/general/margin_top = 52`), not anything strut-related. **If the bar height changes,
this margin must change to match.**

**xfwm4 draws a shadow around every `_NET_WM_WINDOW_TYPE_DOCK` window.** Plank's window
is 2304x272 and keeps that size even while the dock is hidden, so it cast a shadow
across the bottom fifth of the screen over everything. Fixed with
`show_dock_shadow=false`.

**xapp-status-plugin icons are hard-pinned at ~20px.** The wifi and update icons cannot
be enlarged. Ruled out by testing, all with no effect whatsoever:
- panel `icon-size` at 30, 38 and 44
- the plugin's own `symbolic-icon-size` / `color-icon-size`, as both `int` and `uint`
- panel `size` (height) at 52 and 64

Meanwhile pulseaudio and power-manager icons *do* follow panel `icon-size`. This is why
the wifi looks smaller than the speaker and battery, and the only remaining fix would be
to drop nm-applet's tray icon and render wifi through genmon — at the cost of losing the
network-picker popup. Not done.

**xapp-status-plugin holds every XApp status icon in one widget.** nm-applet and
mintupdate both register there, so they render as one contiguous group and cannot be
placed at separate positions in the bar. Within the group they are sorted by bus name
(`mintUpdate_py` before `nm_applet`), which is also not controllable. The only way to
separate them was to take one out of XApp entirely — hence the genmon wifi indicator.

**`xfce4-cpugraph-plugin` defaults to `in-terminal=1`.** Its click command therefore
opens inside a terminal window — this was the stray terminal appearing alongside
System Monitor. The key is `in-terminal`, not the `InTerminal` string in the binary.

**GTK3 ignores `gtk-tooltip-timeout`.** The property still exists and is readable
(value 500), but setting it changes nothing — GTK3 hardcodes the hover delay. Verified
by comparing 120 vs 2000: tooltips appeared at the same moment under both. The panel
tooltip delay is not configurable without patching GTK.

**`hide-systray` needs mintUpdate restarted.** Setting
`com.linuxmint.updates hide-systray true` does nothing until the running `mintUpdate`
process is restarted (`mintupdate-launcher`); until then it keeps its XApp icon
registered and you get two update icons.

**Panel plugins re-append themselves.** Removing a plugin from `plugin-ids` is not
enough — on restart the panel finds the orphaned `/plugins/plugin-N` config and adds it
back to the end of the bar. Always `xfconf-query -c xfce4-panel -p /plugins/plugin-N -r -R`
as well.

**Plugins overwrite xfconf on shutdown.** Setting a plugin's properties while the panel
is running gets clobbered when it next restarts, because the running instance saves its
own state over yours. Sequence that works: `xfce4-panel -q`, set properties, then start
`xfce4-panel` fresh.

**Whisker menu migrated its rc into xfconf.** `~/.config/xfce4/panel/whiskermenu-1.rc`
is read once, imported to `/plugins/plugin-1/*`, then deleted. Configure it in xfconf.

**`xfce4-sensors-plugin` can only be configured through its GUI dialog.** Its keys are
not discoverable in the binary and it shows a literal "Sensors" label until configured.
Replaced with genmon, which runs a script and is fully scriptable.

**WhiteSur's NM icons have a doubled prefix** (`nm-nm-signal-100-symbolic.svg`), so
lookups for `nm-signal-100-symbolic` miss the theme entirely. See
[`icons/generate-wifi-icons.py`](../icons/generate-wifi-icons.py).

**GTK3 recolors symbolic icons by forcing `fill` only, never `stroke`.** An icon drawn
with stroked paths will not follow the panel's foreground colour. Draw filled bands.

**Electron and Firefox draw their own titlebars.** The Claude app will always keep its
buttons on the right; xfwm4 cannot theme client-side decorations.

---


## Backup and revert

Original config was saved **before any changes** to:

```
~/mac-mint-backup-20260831-224309/
```

That contains a tarball of `~/.config/xfce4` (which includes the xfconf XML, so it
restores panel, WM and shortcut settings) plus the original wifi icons.

```bash
~/.local/bin/revert-mac-theme
```

Stops Plank, removes its autostart, restores the XFCE config and restarts the panel and
WM. It does **not** revert the icon theme files — originals for those are in
`wifi-icons-orig/` and `wifi-icons-orig2/` inside the backup directory.

---

## Open / not done

- ~~Wifi icon size parity~~ — **solved** by moving wifi out of xapp into genmon.
  The old symbolic icons under `~/.icons/WhiteSur-light/` are now unused by the panel
  but left in place; `icons/generate-wifi-icons.py` still regenerates them.
- **Claude's tray icon** is a black XEmbed bitmap designed for a light menu bar, so it
  reads as a hole on the dark bar. User said to leave it. The real fix would be
  switching the bar to light with WhiteSur's `--black` panel-font option.
- **Thermals.** The machine was reading 83-88°C during this work. Worth investigating
  separately if it persists at idle.
