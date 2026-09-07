# Control Center — the panel behind the bar icon

<p align="center">
  <img src="images/control-center.jpg" alt="Control Center" width="420">
</p>

The top bar had nine indicators on it. Four of them are readings you glance
at; the rest were switches that happened to be sitting in the open. This is
where the switches went.

Click the two-pill icon between the battery and the clock.

```
bin/control-install          # put it on the bar
bin/control-install --revert # put the old indicators back
```

---

## What is on the bar, and what is behind the click

<p align="center">
  <img src="images/system-bar.jpg" alt="the bar" width="620">
</p>

| on the bar | why |
|---|---|
| systray, xapp | not ours; apps put themselves there |
| CPU sparkline | a reading — you look at it, you do not set it |
| temperature | same |
| Wi-Fi | macOS keeps it out, and a dead network is worth seeing without a click |
| battery | same |
| **Control Center** | everything else |
| clock | |

| behind the click | was |
|---|---|
| Wi-Fi, Bluetooth | `plugin-21` genmon |
| Display brightness | nothing — there was no control for it |
| Sound | `plugin-12`, the XFCE pulseaudio plugin |
| Appearance | `plugin-24` genmon |
| Night Light | `plugin-23` genmon |
| Power profile | `plugin-22` genmon, and `bin/power-menu`'s popup |

The rule the split follows: **a reading stays, a switch moves.** You do not
click a temperature.

CPU and temperature had tiles for about an hour and then lost them. They were
the same numbers the bar already shows, one click further away — the panel is
where you go to *change* something. Both plugins are still in the directory as
`80-cpu.disabled` and `85-temp.disabled`: they are the working examples of the
`meter` kind and the `graph` field, and `mv` puts either one back.

> `bin/power-menu` and `bin/night-menu` still work and are still installed —
> nothing calls them now. They are the pointer-anchored popups the genmon
> icons used to open, and the tiles do the same job with the same backends.

---

## Writing a plugin

Every tile in that screenshot is a separate executable in

```
~/.local/share/mintbook/control-center/plugins/
```

installed from [`control-center/plugins/`](../control-center/plugins). They are
run in filename order, so the leading number is the position. `bin/control-center`
does not know what Wi-Fi is; it runs whatever is in that directory — anything
executable that is not named `*.md` or `*.disabled`. Renaming a plugin to
`60-power.disabled` takes it out of the panel without deleting it.

A plugin answers two verbs:

```
plugin read          prints the tile
plugin set <value>   applies a new value   (only if the tile can be used)
```

`read` prints `key = value` lines. That is the whole format — a plugin is
writable in bash without quoting anything:

```bash
#!/usr/bin/env bash
# 70-awake — keep the screen on. Save it in the plugins directory, make it
# executable, and it is in the panel the next time you open it.
KEY=/xfce4-power-manager/presentation-mode
case "${1:-read}" in
  set) xfconf-query -c xfce4-power-manager -p $KEY -n -t bool \
         -s "$([ "$2" = on ] && echo true || echo false)"; exit 0 ;;
esac
on=$(xfconf-query -c xfce4-power-manager -p $KEY 2>/dev/null)
cat <<EOF
kind = toggle
glyph = sun
title = Keep Awake
value = $([ "$on" = true ] && echo on || echo off)
subtitle = $([ "$on" = true ] && echo 'Screen stays on' || echo 'Sleeps normally')
EOF
```

There is no registry, no manifest and no restart. Drop the file in, open the
panel.

### Fields

| key | for | meaning |
|---|---|---|
| `kind` | all | `toggle`, `segment`, `slider` or `meter`. Required. |
| `title` | all | the label. Required. |
| `subtitle` | all | the smaller line: state, not instructions |
| `glyph` | all | one of the built-in icons, below |
| `value` | all | `on`/`off`, an option key, or 0–100 |
| `option` | segment | `key\|Label`, repeated — 2 to 4 of them |
| `detail` | toggle, meter | a command for the `›` — opens it and closes the panel |
| `live` | all | seconds between re-reads **while the panel is open** |
| `graph` | meter | comma-separated 0–100, drawn as a faded sparkline |
| `span` | all | columns out of 4; the default depends on the kind |
| `accent` | toggle | `#rrggbb` for the lit state, instead of the system blue |
| `skip` | all | `on` — no hardware, no tile. Say nothing rather than show a dead switch. |

A line starting with `{` is parsed as JSON instead, for values that need
newlines or characters `key = value` would mangle.

### Kinds

| kind | looks like | `set` receives | default span |
|---|---|---|---|
| `toggle` | a card with a filled icon, macOS-style | `on` or `off` | 2 |
| `segment` | a labelled row with 2–4 linked buttons | the option key | 4 |
| `slider` | a thick pill you drag or scroll | `0`–`100` | 4 |
| `meter` | a reading, optionally over a sparkline | never called | 2 |

Nothing installed uses `meter` today — `80-cpu.disabled` and `85-temp.disabled`
in the same directory are what it looks like when something does.

### Glyphs

`wifi`, `bluetooth`, `moon`, `sun`, `speaker`, `display`, `cpu`,
`thermometer`, `bolt`, `gear`, `dot`.

They are cairo paths in a unit box, not image files, so they are crisp at any
size and take the panel's own colour in both appearances. Adding one is a
function of about six lines in `bin/control-center` and a line in `GLYPHS`.

### Rules a plugin should follow

- **Be fast.** `read` runs on every open and again on every `live` tick. The
  costs are in the table below; `busctl` is 15 ms, `python3` starting up is
  30-50 ms before it has done anything at all.
- **Never block on `set`.** It runs off the main loop, but a slow one holds the
  tile's next refresh. `60-power` waits up to 2 s for the profile to actually
  change, which is the longest anything here waits and is already noticeable.
- **`skip = on` when the hardware is missing.** `20-bluetooth` does this when
  the SSDC regression has eaten `hci0` — see [bluetooth.md](bluetooth.md).
- **Report the truth, not the request.** Every plugin here reads the state back
  from the system rather than from whatever it last wrote. This is why the
  Power tile appears to change on its own: [`bin/turbo-budget`](../bin/turbo-budget)
  moves the profile between `power-saver` and `balanced` as it grants and
  revokes bursts, and the tile shows whichever is live at that moment.

---

## How it is drawn

One override-redirect GTK window, painted entirely in cairo. Not themed
widgets: the panel sits on top of WhiteSur without inheriting it, and a pill
with its icon clipped against its own fill is not a GTK widget.

- **Override-redirect, like `bin/power-menu`.** genmon spawns the click command
  with `g_spawn_command_line_async`. There is no Gdk event behind it, so xfwm4
  discards a `Gtk.Menu` grab at time 0 and the menu vanishes as it appears.
- **Rounded corners and translucency** come from an RGBA visual and
  `set_app_paintable`. The shadow is sixteen concentric rounded strokes falling
  off in alpha — there is no blur pass anywhere on this machine, by choice.
- **Light and dark** are the same appearance mode as the bar, read from
  `~/.config/mintbook/appearance.applied`.
- **Layout** is a 4-column grid. Tiles are packed left to right and wrap when
  the next one does not fit, so ordering the files orders the panel.
- **Scaling.** XFCE only does integer window scaling, so this display runs
  `WindowScalingFactor=1` with `Xft/DPI` at 168 (see [display.md](display.md)).
  Everything in the source is in 1x units and the cairo context is scaled once
  by `SC = 1.75`. Fonts are set with `set_absolute_size`, in those same units —
  a bare cairo context reports 96 dpi and would otherwise apply the DPI twice.

---

## What it costs

Per-invocation CPU, measured on 2026-09-06 with the machine at roughly half
load, so the absolute numbers run high; the ratios are the point.

**Off the bar's timers:**

| | period | was |
|---|---|---|
| `panel-power` | 3 s | 19.9 ms → 0.66% of a core, continuously |
| `panel-bt` | 5 s | 16.5 ms → 0.33% |
| `panel-night` | 15 s | 110.6 ms → 0.74% |
| `panel-appearance` | 60 s | ~59 ms → 0.10% |
| `panel-control` | 60 s | **59.1 ms → 0.10%** |

The new indicator inherited the appearance job — `appearance-mode --refresh`,
which is what keeps `auto` turning the chrome over at sunset without a daemon —
so its whole cost is that one job. **Net: about 1.7% of a core, given back.**

**Still on the bar:** `panel-cpu` 46.7 ms at 2 s (2.34%), `panel-wifi` 29.7 ms
at 5 s (0.59%), `panel-temp` 123 ms at 30 s (0.41%). The sparkline is now most
of what the bar spends, and most of a third of its 47 ms is `python3`
starting up.

**Opening the panel**, `MINTBOOK_CC_TIME=1` on the same busy machine:

```
7 tiles: 304 ms to import and read, 548 ms to on screen
```

Read one after another the plugins are about 230 ms and the GTK import about
224 ms. They overlap instead: the plugins are launched as subprocesses on the
first line of the file, *before* `import gi`, and collected after.

Dropping the CPU and temperature tiles did **not** make it open faster — nine
tiles measured 287 ms on the same machine and seven measure 304. That is the
point of the overlap: the reads finish inside the import, so the import is the
floor and the plugin count barely shows. Run-to-run variance from load is
larger than the difference.

Nothing installed asks to be `live` any more, so an open panel now costs
nothing until you touch it. A closed one costs nothing at all — which is the
whole argument for a panel over a bar full of indicators.

---

## Gotchas

- **A cairo context is shared with the children.** GTK hands the container's
  `draw` handler the same context it then propagates to every child widget.
  The HiDPI scale set in the window's background handler landed on the tiles as
  well, and everything drew at 1.75x its allocation. `cr.save()` / `cr.restore()`
  around the whole handler.
- **A crescent is not a disc minus a disc.** Under `EVEN_ODD` cairo also fills
  the part of the bite hanging outside the disc, which draws a moon with a
  second lobe. Clip to the disc first, then fill everything but the bite.
- **`system-chrome.env` used to be written with `printf %q`,** so `#ffffff`
  was stored as `\#ffffff`. Sourcing it gave the value back; reading the line
  as text did not, and an SVG with `stroke="\#ffffff"` renders no stroke at
  all and silently falls back to a black fill. That was one invisible icon and
  two black dots here, and — found later — a CPU sparkline that had been black
  on the dark bar the whole time. `bin/appearance-mode` single-quotes the value
  now instead of escaping it, so both ways of reading the file agree.
- **Removing the pulseaudio plugin removes the volume keys with it.** It was
  what grabbed `XF86Audio*`. `bin/volume-key` takes that over, bound in
  `xfce4-keyboard-shortcuts` by the installer, with an on-screen readout
  through `xfce4-notifyd` (`x-canonical-private-synchronous`, so repeated
  presses replace one popup instead of stacking a column).
- **Those bindings have to be written after the panel restarts,** which cost a
  round of confusion. xfsettingsd only attempts the X grab when the property
  changes, so binding a key the still-running pulseaudio plugin holds fails
  silently: the shortcut sits in xfconf looking correct and never fires. The
  installer also deletes each property before writing it, so a re-run is always
  a change.
- **genmon reads the click command's stdout.** Anything a plugin script leaves
  running with an open stdout keeps the panel waiting.

---

## Undo

```bash
bin/control-install --revert
```

Restores the plugin ids saved to
`~/.config/mintbook/panel-ids.before-control-center` on the first install, and
removes the volume-key bindings. `plugin-25` stays registered but unused; the
old genmon `.rc` files were never deleted, so the indicators come back with
their commands intact.
