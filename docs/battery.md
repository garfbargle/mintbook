# Battery — the indicator, the menu, and where the charge went

Three files, one log, no daemon.

| | what | runs |
|---|---|---|
| [`bin/panel-battery`](../bin/panel-battery) | the bar icon, and the sampler | every 5 s, from genmon |
| [`bin/battery-menu`](../bin/battery-menu) | the glass popup behind it | on click |
| [`bin/battery-history`](../bin/battery-history) | the window behind `Battery History…` | on click |

Nothing runs for the history until you open it. The log it reads is already
there, written a line a minute off the bar icon's own tick.

Install with [`bin/battery-install`](../bin/battery-install). `bin/doctor`
checks all of it, and says nothing when it has never been installed — this
machine is fine with `xfce4-power-manager-plugin`, so its absence is not a
fault.

## The bar icon (`plugin-26`, genmon)

It replaces `xfce4-power-manager-plugin` (`plugin-11`), which draws a filled
green capsule at whatever size GTK feels like, has no percentage that matches
the rest of the bar, and opens `xfce4-power-manager-settings` on click.

macOS's battery: an outline, a fill, and a cap. Green above 40%, amber below,
red below 15 — `COLOR=mono` in the config gives the actual macOS look, which is
the panel's own ink and no traffic lights at all.

**The charge and the bolt answer different questions, so they get different
colours.** The fill is the traffic light for how much is left — red, amber,
green, on the percentage alone. The bolt is electric yellow (`#ffe814` on a
dark bar, `#ffcc00` on a light one) for current going in, and it is the only
thing that changes when you plug in.

Charging used to force the fill green, which is *also* 40–100% on battery: a
12% battery looked healthy the moment it was plugged in, and the only thing
separating "plugged in" from "fine" was a small glyph. It no longer does, and
`st` is out of the fill decision entirely — `F` (full, plugged in) reads 100%
and comes out green on the percentage alone. `COLOR=mono` still overrides
everything including the bolt; ink only is the whole point of it.

`bin/battery-menu` makes the same split (`fill_color` and `bolt_color`), so the
glyph in the popup and the charge sparkline agree with the bar.

**Bash, not Python**, for the reason in [desktop.md](desktop.md): `python3`
costs 30–50 ms to start before it has done anything, and this runs every five
seconds forever. A tick is nine sysfs reads and, only when the picture changed,
one 1 KB write — **10–20 ms**. The readings use `read -r v < file` rather than
`$(cat file)`; nine forks every five seconds was the whole difference between a
120 ms tick and a 10 ms one.

The icon is drawn here rather than picked from a set of pre-rendered files the
way Wi-Fi's is, because it has 101 states and a fill width is one integer.
Coordinates are in half-pixels — the `viewBox` is twice the `width`/`height`
attributes — so integer arithmetic, all bash has, still lands on half a pixel.

The percentage is **usable state of charge**: `charge_now / charge_full`, with
the driver's `Full` state shown as 100%. This matters on this Mac because its
raw sysfs `capacity` behaves like charge against `charge_full_design`; using it
directly made an 83%-health battery appear to stop charging around 81–82%.
`capacity` remains a fallback for batteries that do not expose charge counters.

**The bolt is painted over the charge, not punched out of it.** It used to be
negative space over the fill and the fill's own colour past it — two masks, and
a bolt that was green because the charge was. A bolt with a colour of its own
needs neither mask, and the SVG lost its `<defs>` block: yellow reads on the
glass and on all three fills, and painting over the charge is the only version
with no seam where the charge ends, because a mask leaves the fill's rounded
cap showing inside the bolt's notch.

The one fill that could swallow a yellow bolt is amber, nearly the same hue.
That needs the charge to reach the bolt while still under `MID`, which is
36–39% with the percentage off — the number pushes the bolt out to 78%, where
the fill is green — and there the charge has only just touched the bolt's
leading tip. A glass halo punched around the bolt fixes that case and costs the
seam in every other one; it was tried and dropped.

The bolt is always *inside* the body — centred, or against the trailing edge of
the well with the number before it.

**The palette is decided by the ink, not by a second file.** `bin/appearance-mode`
writes `system-chrome.env` before it writes `appearance.applied`, and a tick
landing between the two would draw the new ink against the old palette. White
ink means a dark bar; `#2d3036` means a light one.

> `system-chrome.env` is shell and is written *single-quoted*, not with
> `printf %q`. `%q` stores `#ffffff` as `\#ffffff`, which sources back intact
> but reads as text wrong — and `fill="\#ffffff"` is not a colour, so librsvg
> drops it and paints black. That cost an hour twice. See
> [desktop.md](desktop.md).

### Show Percentage, and the thing that was tried first

With `SHOW_PERCENT=1` the body **grows to hold the number inside it** rather
than standing beside it, and the whole icon is narrower than the old
text-plus-battery was. The digits are the panel's ink over a charge dropped to
`.66`.

**Punching the digits out of the charge was tried first, and is prettier at
100%.** It was dropped because at 30% half a number sits on the fill and half
on the glass, and the two halves are different colours.

Charging with the percentage on used to put the bolt *outside* the body, to
its left, on the argument that the inside was the number's. **That was wrong**
— it read as an icon with an ornament next to it rather than as one icon, and
it was the only state in which the bar's leftmost battery pixel was not the
battery. The bolt now takes the **trailing** end of the well and the number
takes what is left of it: the body grows by the bolt's 18 units plus a gap
(`bw + 23`) rather than the number giving way, and the number re-centres on the
well before the bolt. The icon is 76 px wide in that state against the old 72.5
— 3.5 px for a shape that belongs inside the thing it describes.

The menu writes `SHOW_PERCENT` back to the config and then nudges genmon
(`xfce4-panel --plugin-event=plugin-26:refresh:bool:true`), so the bar changes
under the click that asked for it.

### Config

`~/.config/mintbook/battery.conf`, sourced by `panel-battery` and parsed by the
menu. It is shell, and the menu's parser handles the subset of shell it ever
is — including the trailing `# comment` on a value line, which bash strips and
a naive split does not.

| key | default | meaning |
|---|---|---|
| `SHOW_PERCENT` | `0` | the charge as a number, inside the icon |
| `COLOR` | `traffic` | `traffic` or `mono` — `mono` is the macOS look, panel ink only |
| `LOW` | `15` | below this the fill is red |
| `MID` | `40` | below this it is amber |
| `SAMPLE_EVERY` | `12` | ticks between `/proc` walks — 12 is one a minute. Anything under 1 falls back to 12, and `bin/doctor` warns when the log's real spacing disagrees with it |
| `HISTORY_DAYS` | `7` | how much of the log to keep, **by date** — not by line count, so it means the same thing at any `SAMPLE_EVERY` |
| `PANEL_ID` | `26` | so the menu can tell genmon to repaint |

## The menu (`bin/battery-menu`)

macOS's battery menu, which is: how much charge, how long it lasts, what is
eating it, and one switch.

The switch is the same power profile the Control Center's Power tile sets,
through the same `60-power` plugin, so the two cannot disagree about what is
live. Both read the profile back **from `power-profiles-daemon`** rather than
from what they last wrote, which is why it moves on its own while
[`bin/turbo-budget`](../bin/turbo-budget) is granting and revoking bursts. That
is the tile reporting the truth.

The charge graph is in the menu rather than one click further away, because
that is the question you opened it to answer. Twelve hours of it, a window of
at least twenty points so a quiet hour reads as a slope and not a cliff, and a
stroked top edge so a wide fill reads as a graph and not as a wash behind the
text.

Same chrome as the Control Center and for the same reasons
([control-center.md](control-center.md)): cairo on one override-redirect
window, because genmon spawns its click command with no Gdk event behind it and
xfwm4 discards a `Gtk.Menu` grab at time 0. Unlike the Control Center it is one
`DrawingArea` with a list of rows rather than a widget per tile — it is a fixed
layout, and that is both less code and one allocation instead of nine.
**380–630 ms from click to on screen**, of which the GTK import is most, with
`busctl` already running inside it.

[`bin/wifi-menu`](../bin/wifi-menu) is the same construction, and the two
things it has to do that this does not — resize while open, and take the
keyboard — are in [desktop.md](desktop.md).

## The history window (`bin/battery-history`)

Charge over **3 h / 12 h / 24 h / 3 d**, with the power source as a strip under
the axis and a readout that follows the pointer; three numbers; and a ranked
list of what discharged the battery. Drag across the graph to restrict all
numbers and the application list to that interval; press **R** or Escape to
clear the selection. The graph retains the full range for context.

Energy and CPU counters are clipped proportionally at selection boundaries and
weighted by elapsed time. Intervals with source transitions, inconsistent
timestamps, zero discharge power, resets (`dt=0`), or gaps longer than three
minutes are excluded rather than counted as battery use. The charge line and AC
strip also stop at recording gaps.

### The per-application watts are a fit, not a guess

Every sample carries the measured discharge power *and* the CPU the machine did
in the same minute, so

```
watts = base + k × busy-cores
```

is solved by time-weighted least squares over valid discharging intervals in view, and an
application's energy is `k × its own CPU seconds`. `base` is the floor —
screen, radios, chipset — that no process is responsible for, and it gets **its
own row** rather than being quietly spread over the applications.

Under **twenty** discharging samples or **twenty minutes**, a nonpositive slope,
a negative floor, no CPU variation, or weighted R² below 0.25, app energy is
withheld. Apps then shows **recorded CPU time** and each app's share of recorded
app CPU. A weak positive correlation no longer becomes a confident watt-hour
column. The R² threshold is a display guard, not evidence of causation.

### What it cannot see

In the footer of the window itself, and not nothing:

- **GPU work.** A video decode is watts that no `utime` accounts for.
- **Disk.** Same.
- **A process that holds a radio awake while using no CPU.** On this machine
  that one is not hypothetical — see [hardware.md](hardware.md) on `brcmfmac`
  runtime PM.

Charge and elapsed time are measured regardless; only the per-application
column depends on the fit.

## The log

`~/.cache/mintbook/battery/history`, one line a minute, appended by
`panel-battery` on every `SAMPLE_EVERY`-th tick. Plain text, space separated:

```
ts pct st mW dt dtotal dbusy [app:jiffies ...]
```

| field | is |
|---|---|
| `ts` | unix seconds |
| `pct` | usable charge, 0–100 (`charge_now / charge_full`) |
| `st` | `C` charging, `D` discharging, `F` full/plugged, `U` unknown |
| `mW` | measured power, `current × voltage` |
| `dt` | seconds since the previous sample. **0** on the first line and whenever the gap is over an hour — a suspend is a gap, not a sample — and a 0 is skipped by the fit rather than treated as an instant |
| `dtotal` | all-core jiffies in that interval |
| `dbusy` | of which not idle |
| `app:jiffies` | CPU per **application** in that interval |

An entry is an *application*, not a process: each process is resolved up its
parent chain — stopping at init, at `systemd`/`xfce4-session`/`lightdm`, or
after eight hops — to the thing you would name if asked what was using the
battery. Firefox's dozen content processes arrive as one `firefox-bin` row
rather than twelve rows of `Isolated Web Co`. Anything under 2 jiffies in the
interval (0.03% of a core) is dropped; there are a hundred of those.

Trimmed once an hour to everything newer than `now - HISTORY_DAYS`. The first
line's timestamp decides whether to rewrite at all, so an ordinary hour costs
one `read` and no forks. A real line, from this machine:

```
1788750799 66 D 12619 60 23127 13168 xfwm4:403 xfce4-panel:120 pipewire:181
  kthreadd:294 firefox-bin:1712 claude-desktop:7967 ChatGPT:326 Xorg:1406 …
```

(one line, wrapped here.) 66%, discharging at 12.6 W, 60 seconds since the
last sample, 23 127 all-core jiffies of which 13 168 not idle — and Claude
took 7 967 of them.


The log **survives `battery-install --revert`**; deleting it is a separate
decision and the script says so.

The 2026-09-09 switch from the Mac's design-relative raw percentage to usable
percentage deliberately starts a new graph segment (`dt=0`). Older retained
segments keep their recorded values; the history never rewrites measurements.

### The wear log

`~/.cache/mintbook/battery/health`, **one line a day**, written on the same
hourly pass as the trim:

```
ts charge_full charge_full_design cycle_count temp
1788798315 4260000 5297000 154 456
```

`charge_full` moves by more from the gauge re-estimating it than from a day of
wear, so one reading is not a wear figure and two of them a week apart are not
a curve — which is the argument for writing it down every day rather than
against it. `bin/doctor` reports the ends of it: *"80% of design, 84% 67 days
ago (3 readings)"*. Nothing plots it yet; the history window's Battery health
cell still shows only today's number.

Never trimmed. A line is 40 bytes and a decade is 150 KB.

## What it costs

Measured on this machine, 262 processes, 2026-09-07:

| path | cost |
|---|---|
| a plain tick (read, decide, maybe write the SVG) | **10–20 ms** |
| a tick that also walks `/proc` | **120–230 ms** |
| at `SAMPLE_EVERY=12` | one walk a minute — ~0.25% of a core |

Most of what made the walk that cheap was reading `/proc/pid/stat` with `read`
rather than splitting fifty fields in bash 260 times: that was 13 000 word
splits and most of a quarter-second.

## Install

```
bin/battery-install            # plugin-11 out, plugin-26 in
bin/battery-install --revert   # the XFCE plugin back
```

The swap is **in place**, so the battery keeps its seat between Wi-Fi and the
Control Center. The XFCE plugin is only taken off the bar, never removed, so
`--revert` is a one-line change to an array.

> [`bin/control-install`](../bin/control-install) used to hardcode `11` in its
> `VISIBLE` list, so re-running it after a battery install would have quietly
> put the XFCE plugin back. It reads `PANEL_ID` out of `battery.conf` now,
> defaulting to `11` when the battery indicator has never been installed —
> written as an `if` and not as `[ -r x ] && y`, which under `set -e` exits the
> script when the file is missing, which is exactly the machine that most needs
> the default.

`bin/doctor` checks the three executables, the genmon rc, and the age of the
last sample. A stale log **warns** rather than fails: it means the panel is not
running, which doctor's other checks will have said more directly.

## Open / not done

- **`SAMPLE_EVERY` was left at `2` on this machine.** A docs session set it
  fast to fill the log for screenshots and never put it back: the `/proc` walk
  ran every **10 s instead of every 60** from 2026-09-06 20:56 until
  2026-09-07 — 11 hours at six times the intended cost, ~1.5% of a core
  continuously instead of ~0.25%. 1 752 of the log's 1 774 lines are at that
  rate. **Put back to `12` 2026-09-07.**

  Two things did not catch it, and **both are fixed as of 2026-09-07**.
  `bin/doctor` now checks the median gap of the last 40 samples against
  `SAMPLE_EVERY x 5 s` and warns when they disagree — every check it had before
  only ever asked how *old* the last line was, and stayed green throughout.
  And the trim is by **date** now, not by line count: it used to keep
  `HISTORY_DAYS x 24 x 60` lines, which is `HISTORY_DAYS` days only at exactly
  one line a minute, so at `SAMPLE_EVERY=2` "7 days" silently meant 28 hours.
  The trim had not fired here, so nothing was actually lost — but it would have
  been. `SAMPLE_EVERY` also has a floor now; a hand-edited `0` was a division by
  zero on every tick.
- ~~**The `LIGHT`/`DARK` glass palettes are copied into four files.**~~
  **Done 2026-09-07.** They still are — a popup that has to find and parse a
  file before it can paint is a popup that can fail to paint, and this is the
  same convention `config/firefox/userChrome.css` and the rofi palettes already
  follow. What changed is that the values are now identical in all four and are
  recorded once, in `config/theme/mintbook-glass.ini` under `[PopupLight]` and
  `[PopupDark]`. The drift that was actually there: `bin/battery-history` was
  4/255 lighter on both gradient stops and off by one step on `hair` and
  `tile`, and both it and `bin/control-center` used Apple's **dark**-appearance
  blue (`#0A84FF`) in the light appearance, where it should be `#007AFF`.
- ~~**`Gtk.Window.set_opacity` is deprecated.**~~ **Done 2026-09-07.**
  `Gtk.Window` overrides `Gtk.Widget.set_opacity` with a deprecated variant and
  PyGObject picks the override, so every popup open wrote a warning to stderr.
  Calling `Gtk.Widget.set_opacity(win, …)` explicitly takes the widget one.
- **Health is now recorded, but nothing plots it.** `charge_full /
  charge_full_design` is **80.4% at 154 cycles** on 2026-09-07 (32.4 Wh of a
  design 40.3 Wh). [session-battery-thermals.md](session-battery-thermals.md)
  recorded **84–85% at ~149 cycles** on 2026-09-01. Five cycles cannot be four
  points of wear, so most of that gap is `charge_full` being re-estimated by
  the gauge rather than the pack getting worse — which is exactly why a number
  sampled twice, six days apart, is not a wear curve. **The wear log above
  started 2026-09-07** and fills at one line a day; `bin/doctor` reads its two
  ends. Neither the menu nor the history window draws it, and the history
  window is where it belongs.
