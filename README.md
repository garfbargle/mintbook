# mintbook

Making a 2015 MacBook running Linux Mint look and behave like macOS.

This repo is the record of that work. It exists so a future session with **no prior
context** can understand what was changed, why, and what was already tried and ruled out.

---

## The machine

| | |
|---|---|
| Hardware | MacBook (Retina, 12-inch, Early 2015) |
| CPU | Intel Core M-5Y31 @ 0.9GHz — dual core / 4 threads, **fanless** |
| GPU | Intel HD Graphics 5300 |
| RAM | 7.7 GB |
| Display | eDP-1, **2304x1440** (~226 real DPI) |
| OS | Linux Mint 22.3 "Zena" (Ubuntu 24.04 base) |
| Desktop | **XFCE 4.18**, X11 (not Wayland, not Cinnamon) |
| WM | xfwm4 4.18 with its built-in compositor |

**Two hardware facts drive most decisions here:**

1. The CPU is fanless and thermally limited. It idles around 73°C and hits high 80s
   under light load, so it throttles rather than spinning up a fan. Avoid anything
   with a continuous GPU or CPU cost.
2. `Xft.dpi` is **168** (1.75x) but `Gdk/WindowScalingFactor` is **1**. Only *fonts*
   are scaled — every pixel-sized icon renders at raw size. This is why icons
   consistently look too small until explicitly enlarged.

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
| `icon-size` | 30 |
| `background-style` | 1 (solid colour) |
| `background-rgba` | `0.13, 0.13, 0.14, 0.55` — dark translucent glass |

Plugin order (`plugin-ids`), left to right:

| id | plugin | notes |
|---|---|---|
| 1 | whiskermenu | `button-icon=view-app-grid-symbolic`, no title |
| 7 | separator | `expand=true` — pushes everything right |
| 15 | cpugraph | CPU graph, see below |
| 17 | genmon | CPU temperature, see below |
| 10 | xapp-status-plugin | update checkmark + wifi |
| 8 | systray | Claude's tray icon only |
| 12 | pulseaudio | volume |
| 11 | power-manager-plugin | battery |
| 13 | clock | `%a %-d %b  %H:%M`, Inter 11, `digital-layout=3` (time only) |

### CPU graph (`plugin-15`)

Keys are **kebab-case** (`mode`, `size`, `foreground-1`), and bools are stored as
**ints**. The CamelCase strings inside `libcpugraph.so` are UI labels, not xfconf keys.

```
mode=0 (Normal, not the default LED bars)   size=74   bars=0   border=0   frame=0
per-core=0   command=gnome-system-monitor
foreground-1 = [1.0, 1.0, 1.0, 0.95]   background = [0,0,0,0]
```

### Temperature (`plugin-17`, genmon)

genmon does **not** use xfconf — it reads `~/.config/xfce4/panel/genmon-17.rc`.
It runs [`bin/panel-temp`](bin/panel-temp), which finds `coretemp` **by name** (hwmon
numbering is not stable across boots), prints the package temp, and colours it
white / amber at 80°C / red at 90°C. Tooltip adds SSD and PCH temps.

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

### Window manager (xfwm4)

```
theme=WhiteSur-Light-hdpi        # hdpi variant for the Retina panel
button_layout=CHM|               # close/min/max on the LEFT, Mac order
title_alignment=center
margin_top=52                    # see Gotchas - this is what reserves the top bar
show_dock_shadow=false           # see Gotchas
```

### Spotlight (rofi)

`Cmd+Space` runs [`bin/spotlight`](bin/spotlight), which toggles
`rofi -show drun` with [`config/rofi/spotlight.rasi`](config/rofi/spotlight.rasi):
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
[`icons/generate-wifi-icons.py`](icons/generate-wifi-icons.py).

**GTK3 recolors symbolic icons by forcing `fill` only, never `stroke`.** An icon drawn
with stroked paths will not follow the panel's foreground colour. Draw filled bands.

**Electron and Firefox draw their own titlebars.** The Claude app will always keep its
buttons on the right; xfwm4 cannot theme client-side decorations.

---

## Repo layout

```
bin/spotlight              Cmd+Space launcher toggle
bin/panel-temp             genmon CPU temperature script
bin/revert-mac-theme       restores XFCE config from the backup below
config/rofi/               rofi config + Spotlight theme
config/plank/              dock launcher definitions
config/xfce4-panel/        genmon rc
icons/generate-wifi-icons.py   regenerates the wifi icons
settings/                  xfconf + dconf dumps (reference snapshots)
```

`bin/` mirrors `~/.local/bin/`. `~/.local/bin` is on PATH via `~/.profile`, but only
from the next login after it was first created.

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

- **Wifi icon size parity** with the speaker and battery icons — blocked, see Gotchas.
- **Claude's tray icon** is a black XEmbed bitmap designed for a light menu bar, so it
  reads as a hole on the dark bar. User said to leave it. The real fix would be
  switching the bar to light with WhiteSur's `--black` panel-font option.
- **Thermals.** The machine was reading 83-88°C during this work. Worth investigating
  separately if it persists at idle.
