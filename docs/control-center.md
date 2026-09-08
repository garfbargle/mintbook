# Control Center — the panel behind the bar icon

> 2026-09-07: keyboard navigation and daily conveniences are documented in
> [daily.md](daily.md). Earlier measurements below retain their original scope.

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
| Bluetooth | *since 2026-09-07* — same: "is the speaker connected" is a reading |
| battery | same |
| **Control Center** | everything else |
| clock | |
| software updates | *only when there is one* — see [updates.md](updates.md) |

| behind the click | was |
|---|---|
| Wi-Fi, Bluetooth | `plugin-21` genmon |
| Display brightness | nothing — there was no control for it |
| Sound, output destination | `plugin-12`, the XFCE pulseaudio plugin |
| Appearance | `plugin-24` genmon |
| Night Light | `plugin-23` genmon |
| Power profile | `plugin-22` genmon, and `bin/power-menu`'s popup |

The rule the split follows: **a reading stays, a switch moves.** You do not
click a temperature.

> **Bluetooth went behind the click on 2026-09-06 and came back on the bar on
> 2026-09-07** — under the rule, not around it. The tile was a switch and moved;
> the indicator that replaced it answers *is the speaker connected*, which is a
> reading, which is the same argument Wi-Fi has always had. Both exist now: the
> `20-bluetooth` tile is still the backend, and
> [`bin/bt-menu`](../bin/bt-menu) calls its `set` verb rather than
> `bluetoothctl` so the popup's switch and the tile can never disagree. See
> [desktop.md](desktop.md#bluetooth-menu-binbt-menu).

> **The three three-state switches became three buttons on 2026-09-07.**
> Appearance, Night Light and Power were `segment` tiles: a full-width row
> each, with every option spelled out and one of them lit. Three rows, 194px,
> to say three words. They are `cycle` tiles now — a third of the width each,
> one row for all three, an icon that changes with the state and a tap that
> advances it. Right-click walks back, which is what makes a three-state
> cycle bearable. Measured with `xwininfo`, the panel window went
> **678×1074 → 680×850**: 224px shorter, a fifth of it, on the same nine
> tiles. The two pixels of width are the 12-column grid rounding differently.
>
> **Output became a dropdown on the same day.** It was a `segment`, and a
> segment holds four options, so it was capped at four sinks and had to hoist
> the current default to the front of the list — otherwise a fifth paired
> device could push the destination you were listening to off the tile. Both
> hacks are gone with the cap: `34-audio-output` prints every sink now, in
> pactl's own order.

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
| `kind` | all | `toggle`, `cycle`, `menu`, `segment`, `slider` or `meter`. Required. |
| `title` | all | the label. Required. |
| `subtitle` | all | the smaller line: state, not instructions |
| `glyph` | all | one of the built-in icons, below |
| `value` | all | `on`/`off`, an option key, or 0–100 |
| `option` | segment, cycle, menu | `key\|Label\|glyph\|#accent`, repeated. Everything after the key is optional; only `cycle` reads the last two. A `segment` holds 2–4, a `cycle` 2–4, a `menu` as many as there are. |
| `detail` | toggle, meter | a command for the `›` — opens it and closes the panel. See [Behind the chevron](#behind-the-chevron). |
| `live` | all | seconds between re-reads **while the panel is open** |
| `graph` | meter | comma-separated 0–100, drawn as a faded sparkline |
| `span` | all | columns out of 4; the default depends on the kind |
| `accent` | toggle, cycle | `#rrggbb` for the lit state, instead of the system blue. A `cycle` option's own fourth field beats it. |
| `skip` | all | `on` — no hardware, no tile. Say nothing rather than show a dead switch. |

A line starting with `{` is parsed as JSON instead, for values that need
newlines or characters `key = value` would mangle.

### Kinds

| kind | looks like | `set` receives | default span |
|---|---|---|---|
| `toggle` | a card with a filled icon, macOS-style | `on` or `off` | 6 |
| `cycle` | a third-width card you tap to advance | the option key | 4 |
| `menu` | a row naming its value, which opens a list | the option key | 12 |
| `segment` | a labelled row with 2–4 linked buttons | the option key | 12 |
| `slider` | a thick pill you drag or scroll | `0`–`100` | 12 |
| `meter` | a reading, optionally over a sparkline | never called | 6 |

`70-updates` is the installed example of `meter`, and `80-cpu.disabled` /
`85-temp.disabled` in the same directory are what one looks like with a
`graph` under it.

**`cycle`** is the compact form of `segment`, and the trade it makes is that
you cannot see the options without tapping through them. Three of them fit a
row. The icon is the state — an option's third field names its glyph, its
fourth an accent for the lit disc — and the state is drawn unlit when its key
is one of `off`, `false`, `no`, `0`, `none`, `disabled`. `auto`, `light` and
`balanced` are none of those and none of them are *on*, which is why the rule
is a list of offs rather than the `TRUE` list the `toggle` uses. Left-click
advances, right-click goes back, and the `subtitle` becomes the tooltip: it is
for the one thing the icon cannot say, like which way `auto` has resolved.

**`menu`** is for a list whose length is not up to you. It draws one row with
the current option's label on the right, and opens the rest over the panel.
Nothing is capped.

**Nothing installed uses `segment` any more** — the three tiles that did are
`cycle` now, and Output is a `menu`. The code is still there, the same way
`80-cpu.disabled` is: it is the right widget for a two-choice switch that
should show both choices, and it is four lines of a plugin to ask for one.

### Glyphs

`wifi`, `bluetooth`, `moon`, `sun`, `speaker`, `display`, `cpu`,
`thermometer`, `bolt`, `gear`, `box`, `half`, `leaf`, `gauge`, `check`,
`chevron`, `dot`.

`half` is a disc with one side filled — the shape for a setting that is
following something else rather than being held at a value, which is what
`auto` means on both Appearance and Night Light. `leaf` and `gauge` are the
two ends of the Power cycle; `gauge` is a needle past three quarters rather
than a flame, because this chip throttles rather than burns and the tile
should not promise otherwise. `check` and `chevron` are the dropdown's own.

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

### Behind the chevron

A tile with a `detail` shows a `›`, and the command behind it opens in place of
the panel: the panel closes, and the thing it opened takes its spot.

Wi-Fi and Bluetooth used to open `nm-connection-editor` and `blueman-manager` —
windows, and windows about saved profiles rather than about the network you are
on or the speaker you want back. They open
[`bin/wifi-menu`](../bin/wifi-menu) and [`bin/bt-menu`](../bin/bt-menu) now: the
same popups the bar icons open, the networks in range and the devices paired,
each with its own `Settings…` footer for the things a popup should not try to
be. Both plugins fall back to the old window when the popup is not installed,
which is what keeps `wifi-install --revert` and `bt-panel-install --revert` a
single `rm`.

Two things had to change for that to feel like one panel rather than two.

**The zone is 40 px wide, and you can see it.** The chevron itself is five
pixels of hairline in a tile 159 wide, and the strip that counted as clicking
it was 26 — narrow enough that aiming for *open Wi-Fi* landed on *turn Wi-Fi
off* often enough to be the first thing anyone says about this panel. The strip
is 40 now, and while the pointer is inside it a faint rounded wash is painted
behind the chevron, under the label rather than over it. A `meter` has nothing
to set, so the whole tile is the door and the chevron only says so; a `toggle`
has a switch to protect, so only the strip is. A right-click anywhere on either
opens the detail, as it always did.

**The popup inherits the panel's anchor.** These popups hang off the bar icon
that opened them, which they find by reading the pointer at startup. Reached
from a chevron the pointer is down on a tile instead, and the popup would open
halfway down the screen. So the panel passes `MINTBOOK_ANCHOR=x,y` — the point
it was itself opened at — in the detail command's environment, and
`wifi-menu`, `bt-menu` and `updates-menu` prefer it to the pointer and skip
their own `xdotool` call. Same right edge, same top, measured: panel at
`1170,590` closing, popup at `1186,590` opening, both ending at x 1850.
Anything else behind a chevron ignores the variable and opens where it always
did.

### Audio outputs

The **Output** row names the current playback destination and opens the rest
as a list — every sink, including connected Bluetooth speakers, in the order
pactl reports them. Selecting one makes it the default PipeWire/PulseAudio
sink *and* moves already-playing apps to it, so it takes effect immediately
rather than only for the next app you start. The **Sound** slider and the
hardware volume keys then control that destination. The panel refreshes both
tiles while open, so a speaker that connects or disconnects appears or
vanishes without reopening it.

`MacBook_Speaker_Raw` is filtered out of the list: it is the input to the
4-channel EQ filter, and sending an app there bypasses the tuned speaker path.
`set` also checks that the sink it was handed still exists before making it
the default, so a device that disconnected while the list was open cannot
replace a working destination with a dead name.

> The list is snapshotted when the dropdown opens, not re-read from the tile
> underneath it. The tile asks to be `live = 2`, and a list that reordered or
> shrank under an open menu would hand the click to a different device than
> the one being pointed at.

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
- **Layout** is a 12-column grid. Tiles are packed left to right and wrap when
  the next one does not fit, so ordering the files orders the panel. It was
  four columns until `cycle` arrived, and a third of four columns is not a
  column. Spanning *n* columns is *n* × `COLW` plus the *n*−1 gaps it
  swallows, so 6-of-12 is exactly the width 2-of-4 was: every tile that
  existed before the grid changed is the same size after it.
- **The dropdown is an overlay, not a second window.** A `Gtk.Menu` needs a
  grab the panel is already holding, and another override-redirect window
  would need its own placement, its own shadow and its own dismissal. It is
  one `DrawingArea` in a `Gtk.Overlay`, covering the panel, hidden until it is
  asked for, treating a click anywhere outside its own rectangle as a
  dismissal. It opens with the live row *on top of* the tile rather than below
  it, the way a macOS pop-up button does.
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

> Those seven are the tile set as it was on 2026-09-06. It is nine now
> — Output and Sound are separate tiles — and `34-audio-output` asks to be
> `live = 2`, so the line below about nothing asking to be live is about that
> day, not this one.
>
> **The 2026-09-07 tile rewrite was not timed against this.** `cycle` and
> `menu` draw less than the three segments and the segment they replaced, and
> the same nine plugins run either way, so there is no reason to expect a
> change — but the machine was busy enough while they were being written that
> the same panel measured 570–670 ms to read where this table says 304, and a
> number taken under that load would not be comparable to the one above it.
> The win being claimed is 224 pixels of height, which `xwininfo` measures the
> same on a busy machine as an idle one.

Nothing installed asks to be `live` any more, so an open panel now costs
nothing until you touch it. A closed one costs nothing at all — which is the
whole argument for a panel over a bar full of indicators.

### What the floor is made of

Measured 2026-09-07, machine idle, warm page cache. Every popup behind the bar
— this one, `bt-menu`, `wifi-menu`, `battery-menu` — is a fresh Python process
per click, and pays the same startup before it can draw anything:

| phase | ms | |
|---|---|---|
| fork/exec + interpreter start | ~55 | |
| compile this file — 33–47 KB of source | ~35 | before `T0` |
| `import gi` + `require_version` | ~65 | |
| `from gi.repository import Gtk, Gdk, GLib, Pango, PangoCairo` | ~190 | |
| `Gtk.init` — X connect **and parse the GTK theme** | ~200 | |
| realize + first Pango layout (fontconfig) | ~40 | |
| **before any of this file's own code runs** | **~585** | |

The first two are both before `T0`, so no `MINTBOOK_*_TIME` number contains
them. The typelib line was first measured at ~225 and settles at ~190 when
runs are interleaved rather than taken back to back; treat run-to-run load as
worth ±40 on any single figure here.

Then the reads, the layout, the X map and the compositor. That is the ~1 second
between the click and the popup, and it is why all four feel the same: the part
they share is most of it.

`import gi` is ~65 ms warm and ~220 cold — the 190 ms in docs/desktop.md is a
cold read of a smaller import set, not this one.

**~120 ms of that was the theme.** `Gtk.init` parses the GTK stylesheet, and
WhiteSur's `gtk.css` is 400 KB. Interleaved, five runs each, timing `Gtk.init`
alone:

```
WhiteSur 367 ms   Adwaita  77 ms      (first, cold)
WhiteSur 183 ms   Adwaita  69 ms
WhiteSur 205 ms   Adwaita 114 ms
WhiteSur 186 ms   Adwaita  66 ms
WhiteSur 191 ms   Adwaita  62 ms
```

None of the four popups reads a rule from it. Everything visible is cairo on a
`DrawingArea`; the only widgets are a `POPUP` window and a `Box`; there is no
`get_style_context` and no `CssProvider` anywhere in them; even the Wi-Fi
password field is drawn rather than being a `Gtk.Entry`; and dark/light comes
from `appearance.applied`, not from the GTK theme. The 400 KB was parsed and
thrown away, once per click.

So each of the four now sets `GTK_THEME=Adwaita` before `import gi`, which is
the last moment it can be set — `Gtk.init` reads it, and a theme cannot be
unset afterwards. `setdefault`, so `GTK_THEME=WhiteSur-Light control-center`
still A/Bs it. Interleaved, four runs each, `MINTBOOK_*_TIME=1` to on screen:

| | WhiteSur | Adwaita | |
|---|---|---|---|
| `control-center` | 722 806 978 709 | 580 648 571 690 | −150 ms |
| `wifi-menu` | 673 651 617 668 | 452 603 468 454 | −200 ms |
| `battery-menu` | 505 493 566 542 | 299 348 405 362 | −170 ms |
| `bt-menu` | 567 364 569 432 | 444 245 510 369 | −95 ms |

**What was not established.** Byte-comparing an `xwd` of each popup under both
themes: `control-center` came back identical, and the other three differ — but
their captures are 3.5 s apart and their contents are live (charge, signal,
scan results), and the noise floor for that test was never measured, so those
three differences are unattributed. The argument for no visual change is the
grep, not the capture. The claim to check, if a difference ever shows up, is
that one of them touches a themed widget after all.

### What was measured and left alone

The theme was the only free win. Three more were measured on 2026-09-07 and
all three were declined; they are written down so the next person does not
re-derive them.

**Python never caches bytecode for the script you name on the command line.**
It caches every *imported module* into `__pycache__`, but `__main__` is
recompiled from source on every launch, and these files are 33–47 KB:

```
compile 47 KB source :   32.9 ms
unmarshal cached .pyc:    0.7 ms   (75 KB)
```

So ~33 ms of every click recompiles bytes that did not change — 40 ms for
`wifi-menu`, 34 for `control-center`, 33 for `battery-menu`. It cannot be
fixed inside one file: the compile has already happened before any of that
file's own code runs, so the logic that would avoid it cannot live in the file
it is avoiding. It needs each script split into a ~5-line stub plus a module
Python is willing to cache. **Declined** — 33 ms is not worth turning "seven
small executables in a directory" into launchers plus modules, which is the
property the whole design is for.

**Dropping the `Gtk` typelib.** `Gtk` is most of the import; `Gdk` + `Pango` +
`PangoCairo` without it is cheaper. Interleaved, five runs:

```
with Gtk 189 ms    without Gtk 114 ms
with Gtk 192 ms    without Gtk 185 ms
with Gtk 311 ms    without Gtk 152 ms
with Gtk 221 ms    without Gtk 168 ms
with Gtk 216 ms    without Gtk 103 ms
```

Median ~216 → ~152. The second row is the honest one: the gap is noisy enough
not to trust ~60 ms as more than an order of magnitude. And collecting it means
rewriting the window and mainloop layer in four files from `Gtk.Window` /
`Gtk.DrawingArea` / `Gtk.main()` to raw `Gdk.Window` + `GLib.MainLoop` —
touching exactly the override-redirect and grab-at-time-0 behaviour in
**Gotchas** below. **Declined:** the least certain win on the list, for the
riskiest change.

**`python3 -S`, to skip `site`.** Saves ~20 ms by not building the path, and
then `gi` is not on the path:

```
ModuleNotFoundError: No module named 'gi'
```

The 0.03 s it appeared to take was the crash, not a fast start. **Dead end.**

**A resident process** — a daemon holding Gtk imported, or a zygote forking
after the import — is the only thing that removes the ~190 ms typelib import,
because that is `libgirepository` building Python wrappers fresh in every
process and no environment variable moves it. **Not pursued**, and its RAM cost
was never measured, so there is no number here to argue from. The remaining
~380 ms floor of interpreter, typelib and `Gtk.init` is the price of a process
per click, and it is being paid deliberately.

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
- **A widget that has never been shown has never been allocated.** The
  dropdown clamps itself inside the panel, and it asked its own
  `get_allocated_height()` for the bound. A `Gtk.Overlay` child created with
  `set_no_show_all(True)` reports 1×1 until the first time it is mapped, so
  the clamp pinned every first open to the top of the panel and only the
  second one landed on the tile. It asks the toplevel window instead.
- **genmon reads the click command's stdout.** Anything a plugin script leaves
  running with an open stdout keeps the panel waiting.
- **The pointer has to be read before the GTK import, and synchronously.**
  Every popup anchors itself to the pointer, and the pointer is the icon —
  clicking the icon is the only way to open one. Reading it after the import
  read it ~590 ms late, so you could aim, click, move on, and watch the popup
  open wherever the mouse had got to. Moving that read into a `Popen` at the
  top, the way the `busctl` readings are hidden inside the import, does **not**
  fix it: the child is descheduled behind this process's own CPU-bound import
  — two cores, and one of them is the import — so xdotool sampled *after* it
  and returned the same late position. Its own output is the proof; clicking
  at x=2100 and moving to 700 gave `X=700\nY=900`. `subprocess.run` at the top
  instead, ~12 ms, not hidden behind anything. The `busctl` reads only have to
  *finish* before use, which is why hiding those works; this one has to
  *sample* early, which is a stronger thing to ask.

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
