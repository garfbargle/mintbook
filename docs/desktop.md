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
lm-sensors gnome-system-monitor btop redshift
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

### Shared glass palette

[`config/theme/mintbook-glass.ini`](../config/theme/mintbook-glass.ini) is the
canonical source for the pearl surface colour: `#E5E7EA` at the lit edge to
`#CACDD2` below it. It also holds the darker, icon-safe system-bar derivative.
Each renderer has its own format, so the palette is translated rather than
shared as literal CSS: Firefox uses `rgb()` values, Plank uses `R;;G;;B;;A`, and
XFCE panel stores normalized RGBA doubles.

### Top bar (xfce4-panel, `panel-1`)

| Setting | Value |
|---|---|
| `position` | `p=6;x=0;y=0` (top, full width — `p=6` is what makes it *snap*, see Gotchas) |
| `size` | 52 |
| `icon-size` | 36 |
| `background-style` | 1 (solid colour) |
| `background-rgba` | `0.357, 0.376, 0.412, 0.702` — pearl-derived slate glass; leaves light panel icons legible |

Plugin order (`plugin-ids`), left to right:

| id | plugin | notes |
|---|---|---|
| 1 | whiskermenu | `button-icon=view-app-grid-symbolic`, no title |
| 7 | separator | `expand=true` — pushes everything right |
| 8 | systray | "the rest" — Claude; blueman is hidden here (see Bluetooth below) |
| 10 | xapp-status-plugin | mintUpdate, only when updates are available |
| 19 | genmon | CPU sparkline |
| 17 | genmon | CPU temperature |
| 18 | genmon | Wi-Fi |
| 21 | genmon | Bluetooth |
| 23 | genmon | night light |
| 12 | pulseaudio | volume |
| 22 | genmon | power profile (Power Saver / Balanced / Sustained) |
| 11 | power-manager-plugin | battery |
| 13 | clock | ` %a %-d %b  %H:%M  `, Inter 11, `digital-layout=3` (time only) |

Right-to-left: **date/time, battery, power profile, volume, night light,
bluetooth, wifi, temperature, CPU, then the rest.** This follows the macOS
convention — the clock is furthest right with the battery beside it, then the
power mode, then volume, then night light with Wi-Fi / Bluetooth. Informational
items (temp, CPU) sit inboard of the system status group, and anything
unrecognised accumulates right-to-left from the far left of the group.
mintUpdate's own icon appears in the xapp group (plugin-10) only when there
are updates.

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

State lives in `~/.cache/mintbook/`, written via a temp file and `os.replace`
so a half-written file is never read. It is **two** files, and the split is the
point:

- `cpu.state` — previous jiffies, the history, the tick counter and the cached
  top-5 rows. ~320 bytes, rewritten every tick.
- `cpu.procs` — the per-process time table and the `/proc/stat` total it was
  taken against. ~5.6 KB, rewritten every **third** tick (`PROC_EVERY`).

The sparkline reads two numbers out of `/proc/stat`, which is cheap. The tooltip
opens `/proc/<pid>/stat` for every process on the machine, which is not — it was
running at 2 s alongside a 5.9 KB rewrite of the whole table. Because the
process delta is measured against the total stored *next to the table* rather
than against the previous tick, the percentages stay correct over the longer
interval. The tooltip's `CPU` header is still live every tick; only the
per-process rows can be up to 6 s old, and nothing reads them until the pointer
is over the plugin.

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

### Update manager (mintUpdate tray)

A genmon replacement (`plugin-20` / `bin/panel-update`) was tried and **reverted**.
Two independent failures stacked:

1. The script read `~/.linuxmint/mintupdate/updates.json`, which stays `{"updates": {}}`
   even when Update Manager has a real list, so the genmon icon never switched to
   "pending" — it just sat there.
2. `gsettings set com.linuxmint.updates hide-systray true` does **not** hide the
   stock icon forever. The preference label is *"Only show a tray icon when updates
   are available or in case of errors"*. mintUpdate still calls `set_status(..., True)`
   whenever updates exist, so the old XApp icon appeared next to the dead genmon one
   as soon as there was something to install.

mintUpdate's own XApp icon in `plugin-10` is the indicator again. `hide-systray`
stays **true**, so the bar is clean when the system is up to date and the stock icon
appears (still ~20px) when there is work to do. Click it to open Update Manager.

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

### Bluetooth indicator (`plugin-21`, genmon)

Runs [`bin/panel-bt`](../bin/panel-bt), icons from
[`icons/generate-bt-genmon.py`](../icons/generate-bt-genmon.py).

Blueman's tray icon is a StatusNotifier item, so it lands in the systray plugin
(plugin-8) alongside Claude and **cannot** be placed on its own. Same constraint as
nm-applet / mintUpdate in xapp-status-plugin: one widget, one group. The genmon
indicator sits immediately left of volume / right of wifi; click opens
`blueman-manager`. Polls BlueZ over D-Bus every 5s. Dim icon when powered off;
full white when on; tooltip lists connected devices.

It is a bash script that reads one `dbus-send` reply with awk. It used to be
Python importing `gi.repository`, and that import alone was 190 ms of the
script's 197 ms — essentially the whole cost was loading GObject introspection
in order to make a single call. "No adapter" is answered from
`/sys/class/bluetooth/hci*` before D-Bus is touched at all, which is also the
state this machine lands in when the SSDC regression eats hci0.

blueman-applet stays running (pairing / secret agent). Only its tray icon is hidden,
via `/plugins/plugin-8/hidden-items = blueman`.

### Power profile (`plugin-22`, genmon)

xfce4-power-manager **4.18 has no power-profiles-daemon UI** — the settings dialog
is lid / sleep / brightness, and the battery plugin is charge only. The switcher
is therefore another genmon icon, immediately left of the battery, same 30px
canvas as wifi/bt.

Runs [`bin/panel-power`](../bin/panel-power). Click opens [`bin/power-menu`](../bin/power-menu),
an override-redirect popup (a Gtk.Menu dies immediately — genmon clicks have no
Gdk event, so xfwm4 rejects the grab). **Power Saver / Balanced / Sustained.**
That calls `mintbook-power-apply` via `/run/mintbook-power/want` (a root
systemd path unit), so there is **no password**. `max_perf_pct` is 70 for Saver,
100 for Balanced and **75** for Sustained — see
[hardware.md](hardware.md#the-three-profiles) for why Sustained is not 100.
Plug or unplug still runs the automatic AC/battery policy.

The tooltip is the **current** profile and a one-line hint (what that profile
does to the CPU), not two different modes. "Turbo allowed" means the 2.4 GHz
ceiling is unlocked; it is not a fourth profile.

Icons from [`icons/generate-power-genmon.py`](../icons/generate-power-genmon.py)
(Adwaita `power-profile-*-symbolic` paths, baked `#ffffff`).

The indicator is a bash script reading `ActiveProfile` with `busctl`. It used
to be Python shelling out to `powerprofilesctl get`, which meant starting a
Python interpreter in order to start a *second* Python interpreter —
`powerprofilesctl` is itself Python. That was 350 ms a run, at a 3 s period.

CLI is still `powerprofilesctl get` / `pkexec mintbook-power-apply …`. The
period stays at 3 s: `power-menu` already forces an immediate refresh with
`xfce4-panel --plugin-event=genmon-22:refresh:bool:true` after a click, so the
period only governs how fast the icon notices a charger, and stretching it
would buy a few seconds of CPU an hour in exchange for a laggy icon.

### Night light (`plugin-23`, genmon)

Sunset-to-sunrise colour temperature. **redshift** writes the RandR LUT;
**redshift-gtk** was tried first and rejected (XApp lightbulb at ~20px in
plugin-10, stock menu). The indicator is a 30px moon, same canvas as wifi/bt,
immediately left of volume.

```
sudo apt install redshift
bin/night-install
```

Config is [`config/redshift.conf`](../config/redshift.conf) → `~/.config/redshift.conf`:

| | |
|---|---|
| Location | San José **9.93 N, 84.08 W** (manual; Costa Rica is small enough) |
| Day | 6500 K |
| Night | 3500 K |
| Method | RandR gamma on `eDP-1` |

Click opens [`bin/night-menu`](../bin/night-menu) (override-redirect, same
reason as the power menu). Three modes:

| | |
|---|---|
| **Auto** | Follow the sun. Default. |
| **On** | Lock night temperature (`redshift -t 3500:3500`) |
| **Off** | Kill redshift, `redshift -x` |

Mode is `~/.config/mintbook/night.mode`. Autostart is
[`config/autostart/mintbook-night.desktop`](../config/autostart/mintbook-night.desktop)
→ `night-apply` with the saved mode. The moon is full white while the warm LUT
is on, 35% when it is not (off, or auto during the day). Tooltip is the mode
and the current period/temperature from `redshift -p`.

Do **not** launch the Redshift app from the menu — that is redshift-gtk, and
its tray would come back next to mintUpdate.

### What the bar costs (2026-09-04)

The status bar was the single most expensive piece of software running on this
machine. Summed from `cutime` on the six genmon wrappers, it had spent **800
seconds of CPU in a 1 h 55 m session — 11.6% of one core, continuously**, to
draw six glyphs.

| plugin | period | CPU in that session |
|---|---|---|
| `panel-power` | 3 s | **401 s** |
| `panel-cpu` | 2 s | 159 s |
| `panel-bt` | 5 s | 152 s |
| `panel-wifi` | 5 s | 38 s |
| `panel-night` | 15 s | 28 s |
| `panel-temp` | 30 s | 23 s |

Two causes, both avoidable, and neither one about how often the plugins ran:

- **`panel-power` started two Python interpreters per tick.** It was Python, and
  it shelled out to `powerprofilesctl`, which is *also* Python. 350 ms to read
  one D-Bus string.
- **`panel-bt` imported `gi.repository`** to make a single D-Bus call. That
  import is 190 ms of a 197 ms script.

Measured costs on this chip, which is what the rewrites were chosen from:

| | cost |
|---|---|
| `bash -c :` | 7 ms |
| `python3 -c pass` | 50–53 ms |
| `cat` a sysfs file | 5 ms |
| `dbus-send` one call | 10 ms |
| `busctl get-property` | 15 ms |
| `import gi.repository` | 190 ms |
| `powerprofilesctl get` | 264 ms |

So `panel-power` and `panel-bt` became bash, reading `busctl` and `dbus-send`.
Both emit byte-identical output to the Python they replaced. `panel-cpu` has to
stay Python — it generates the SVG — so instead its `/proc` walk moved to every
third tick.

Interleaved A/B, same load, per invocation:

| | before | after | |
|---|---|---|---|
| `panel-power` | 367 ms | **29 ms** | 12.7x |
| `panel-bt` | 236 ms | **23 ms** | 10.3x |
| `panel-cpu` | 79 ms | **65 ms** | 1.2x |

At the unchanged periods that is **23.2% → 7.8% of one core, a 3x cut**, with no
change to what the bar shows or how fast it reacts.

> Measuring this needs care. A straight before/after of the genmon wrappers
> reads 11.6% → 7.8%, which *understates* the win: the second window was ~1.8x
> busier than the first. The three plugins that were not touched are the proof
> and the control — `panel-night` went 0.41% → 0.94% and `panel-wifi` 0.56% →
> 0.92% while their code did not change at all. Per-invocation A/B under one
> load is the number to trust.

**The periods were left alone.** Stretching `panel-power` from 3 s to 10 s would
save about 20 s of CPU across a two-hour session and cost up to 10 s of lag
before the icon notices a charger. After the rewrite the period is no longer
where the cost is. `power-menu` already forces an immediate refresh on click.

What is left is mostly `python3` starting up: `panel-cpu` is now roughly half of
the bar's remaining cost, and 50 of its 65 ms is the interpreter. Getting that
back means not being Python, which for the SVG renderer is a bigger change than
it is worth today.

### Dock (Plank)

Launchers live in **`~/.config/plank/dock1/launchers/`** — *not* in
`~/.local/share/plank/`, which is where the themes go. The ordered list is
authoritative in dconf under `dock-items`; adding files alone does nothing.

```
theme=WhiteSur   position=bottom   icon-size=80   zoom-enabled=true
zoom-percent=150   hide-mode=intelligent   auto-pinning=false
```

Theme copied from [`config/plank/WhiteSur/dock.theme`](../config/plank/WhiteSur/dock.theme)
to `~/.local/share/plank/themes/WhiteSur/dock.theme`. It retains WhiteSur's
geometry and animation, with its fill translated from the shared pearl palette.

### Firefox glass chrome

Firefox's **Customize Toolbar → Title Bar** option is off, so its window
controls share the tab-strip row instead of taking a separate xfwm4 titlebar.
The tab strip and navigation bar are genuine translucent glass on this X11
desktop; the working stylesheet is
[`config/firefox/userChrome.css`](../config/firefox/userChrome.css), installed
as `~/.mozilla/firefox/2e8csxhy.default-release/chrome/userChrome.css`.

Firefox will only load the file when this preference is present in the profile's
`user.js` (the profile must then be fully restarted):

```js
user_pref("toolkit.legacyUserProfileCustomizations.stylesheets", true);
```

The critical rule is the transparent `body` / `#main-window` backing layer.
Firefox otherwise pre-blends the translucent toolbar against its opaque white
chrome document, which looks like a solid white bar even though the X11 window
has an ARGB visual. The style intentionally has **no `backdrop-filter`**:
testing it caused a long first paint on the Broadwell GPU.

This is a supported preference plus an **unsupported userChrome CSS hack**.
Firefox UI selectors can change with a release, so keep this file small and
expect to check it after an update.

#### What can share the treatment

| Surface | Glass route | Status here |
|---|---|---|
| Firefox (ARGB, client-side chrome) | Per-app userChrome CSS | Working |
| XFCE panel and Plank | Their own RGBA/theme settings | Already translucent/fake-glass |
| Ordinary xfwm4-decorated windows | xfwm4 theme/frame opacity | Can affect only the server-drawn frame |
| ChatGPT and other opaque Electron CSD windows | The application must create a transparent window and render a translucent header | Not available as a desktop-wide setting |

Xfwm4 cannot restyle a client-side header, and a compositor cannot isolate one
part of an opaque Electron window. Compton is installed but intentionally not
running: replacing xfwm4's compositor and applying an opacity rule would fade
or blur an entire Electron window, including its content, rather than create a
good header-only glass effect. Keep the system chrome on its native theme path;
only add app-specific glass when that app exposes a transparent surface.

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
margin_top=52                    # fallback only; the panel's strut is the real reserve. Gotchas.
show_dock_shadow=false           # see Gotchas
```

### Spotlight (rofi)

`Cmd+Space` runs [`bin/spotlight`](../bin/spotlight), which toggles
`rofi -show drun` with [`config/rofi/spotlight.rasi`](../config/rofi/spotlight.rasi):
centred, 52% wide, 14% from the top, translucent dark, rounded 24px, fuzzy matching.

Sizes in the theme are **real device pixels** — rofi 1.7.5 lays `px` out
literally and does not scale it by `Xft.dpi`, so on this 168dpi panel a
96dpi-sized theme comes out at ~0.6x. The theme is written ~1.7x up to land at
macOS Spotlight's apparent size: 52px app icons, 80px rows, `Inter 30` in the
search field, `Inter 18` in the list. Fonts follow the same rule (rofi renders
them at 96dpi here), so a point size in this file is not the point size you
would use in a GTK app.

### Keyboard

```
/commands/custom/Super_L                    = /bin/true              # frees the Super key
/commands/custom/<Super>space               = ~/.local/bin/spotlight
/commands/custom/<Shift><Super>numbersign   = ~/.local/bin/screenshot -f  # Cmd+Shift+3
/commands/custom/<Shift><Super>dollar       = ~/.local/bin/screenshot -r  # Cmd+Shift+4
/commands/custom/<Shift><Super>percent      = ~/.local/bin/screenshot -w  # Cmd+Shift+5
/commands/custom/<Shift><Super>asciicircum = ~/.local/bin/appearance-snapshot tweak  # Cmd+Shift+6
```

Copy/paste is deliberately unchanged: **Ctrl+C / Ctrl+V** everywhere,
**Ctrl+Shift+C / Ctrl+Shift+V** in the terminal.

### Screenshots

This keyboard has **no Print key**, so the stock XFCE `Print` /
`Shift+Print` / `Alt+Print` bindings are unreachable. Super is already the
Cmd-like key (Spotlight), so the macOS chords are the ones that work:

| Chord | What | Saved as |
|---|---|---|
| **Cmd+Shift+3** | whole screen | `~/Pictures/Screenshots/Screenshot_*.png` |
| **Cmd+Shift+4** | drag a region (click, drag, release) | same |
| **Cmd+Shift+5** | current window | same |
| **Cmd+Shift+6** | desktop, Firefox, and ChatGPT appearance set | `~/Pictures/Appearance/<timestamp>_tweak/` |

They run [`bin/screenshot`](../bin/screenshot) → `xfce4-screenshooter -$mode -s $file`,
then a **160ms full-screen white flash**. Confirmed 2026-09-01: fullscreen write
of a 2304×1440 PNG in under a second, flash visible after the file exists.

The old Print bindings stay in xfconf in case an external keyboard appears.

`Cmd+Shift+6` runs [`bin/appearance-snapshot`](../bin/appearance-snapshot).
It saves `desktop.png`, then visible `firefox.png` and `chatgpt.png`, and restores
the previously focused window. For an intentional comparison label, run
`appearance-snapshot before` and `appearance-snapshot after` from a terminal;
the output path is printed for each set. It has no flash, dialog, upload, or
additional screenshot dependency.

#### The snap flash

macOS-style camera blink so it is obvious a shot was taken. Implemented as a
GTK3 window, not a compositor fade and not an xrandr brightness spike (the
latter would cost heat on this fanless Core M).

- **After the save**, so the white frame is not in the PNG. Region/window
  modes flash only if the file exists (cancel → no flash).
- **Override-redirect** + `NOTIFICATION` hint, skip-taskbar/pager, no focus.
  `win.fullscreen()` was not used: xfwm4 would animate that in.
- **160ms solid white**, then destroy. 90ms was too easy to miss at 60 Hz.
  No opacity fade — `set_opacity` needs the compositor and was extra moving
  parts for no gain.
- Flash failures (`python3 … || true`) must not undo a successful save.
- Geometry from `Gdk.Display.get_primary_monitor()`, not deprecated
  `Gdk.Screen.get_width()`.

No shutter sound. `xclip` is still not installed; nothing is copied to the
clipboard.

#### Why the first bind did nothing (two independent bugs)

**1. XFCE never matched the chord.** `xmodmap` on this US ANSI board:

```
keycode 12  3   numbersign
keycode 13  4   dollar
keycode 14  5   percent
```

`gtk_accelerator_parse("<Super><Shift>3")` yields keyval `3` plus Shift+Super.
That is also what `gtk_accelerator_name` prints (`<Shift><Super>3`). It is **not**
what the live event is.

libxfce4ui's grabber (`xfce-shortcuts-grabber.c`, the bug #8744 workaround):
`gdk_keymap_translate_keyboard_state` turns Shift+3 into keyval `numbersign` and
marks Shift as consumed; the grabber then **puts Shift back** into the modifier
mask. The lookup key is therefore `<Shift><Super>numbersign`, not
`<Super><Shift>3`. X may still grab keycode 12; the filter does not match, so
the command never runs. Same for `dollar` / `percent`.

The working xfconf properties are exactly those lookup names:

```
/commands/custom/<Shift><Super>numbersign  ~/.local/bin/screenshot -f
/commands/custom/<Shift><Super>dollar      ~/.local/bin/screenshot -r
/commands/custom/<Shift><Super>percent     ~/.local/bin/screenshot -w
```

**2. Even a correct command hung on a hidden dialog.**
`xfce4-screenshooter -f` with no `-s`, or `-s` pointing at a **directory**,
waits on the save/copy GTK window. On this HiDPI panel that window does not
reliably appear, so the process sits there until killed. `-s` must be a
**file path**. `bin/screenshot` always passes one.

#### Ruled out

- **The tool.** `xfce4-screenshooter -f -s /tmp/foo.png` writes a valid
  2304×1440 PNG immediately. No extra package (`scrot` / `maim` / `import`).
- **Super_L = /bin/true eating chords.** `Cmd+Space` (Spotlight) still fires.
  Only the shifted number keys were wrong.
- **Clipboard (`-c`).** `xclip` is not installed. `-f -c -s <dir>` sat for ~30s
  and then wrote a file anyway; skip `-c`.
- **Reordering modifiers to `<Shift><Super>3`.** Same keyval `3`. Still not
  `numbersign`.


---

## Gotchas — things that cost real time

**The panel set no struts, because its snap position was wrong.** For most of this
config's life `_NET_WM_STRUT_PARTIAL` was absent on every window and `_NET_WORKAREA`
was the full 2304x1440. The cause was `position = p=1;x=0;y=0`. The `p=` field is
xfce4-panel's *snap* position, not a coordinate — the `x=0;y=0` put the bar at the top
of the screen, but `p=1` told the panel it was not snapped to the top edge, so
`struts_edge` came out as none and it declined to publish a strut. It looked right and
behaved wrong. **`p=6` is the top edge.** Measured, with everything else unchanged:

| `p=` | panel geometry | strut |
|---|---|---|
| 0, 1 | `2304x52+0+0` | property never set |
| 2, 6, 9 | `2304x52+0+0` | `top = 52` ✔ |
| 5 | `2304x52+0+0` | set, but all zeros |
| 3, 7 | `2304x52+0+694` | all zeros (bar jumps to mid-screen) |
| 4, 8 | `2304x52+0+1388` | `bottom = 52` (bar jumps to the bottom) |

`enable-struts` was `true` the whole time and toggling it changed nothing — the snap
position is checked first. Fixed 2026-09-04; `_NET_WORKAREA` is now `0, 52, 2304, 1388`
and survives `xfce4-panel -r`.

**Why this mattered, and what `margin_top` does not cover.** xfwm4's workspace margin
(`/general/margin_top = 52`) fixes xfwm4's *own* placement and maximization, and that is
all. It is never published to `_NET_WORKAREA` — verified by setting the margin to 200 and
watching the root property stay full-screen. So every app that positions its own windows
by reading `_NET_WORKAREA` — Electron (Claude, Cursor), Chrome, Qt, Java — believed it
had all 1440 rows and opened its windows over the bar. That is the "window opens with a
gap, but not a 52px one" bug: those apps were insetting from y=0, not from y=52.

The two settings do **not** stack, so keeping both is safe: xfwm4 takes the larger of
margin and strut, verified at `margin_top` 0 / 52 / 200 against a 52px strut (frame
landed at y=52, 52, 200). `margin_top` stays as a fallback in case the strut ever
breaks again. **If the bar height changes, `margin_top` must change to match** — the
strut follows the panel's own height automatically.

**xfwm4 draws a shadow around every `_NET_WM_WINDOW_TYPE_DOCK` window.** Plank's window
is 2304x272 and keeps that size even while the dock is hidden, so it cast a shadow
across the bottom fifth of the screen over everything. Fixed with
`show_dock_shadow=false`.

**xapp-status-plugin icons are hard-pinned at ~20px.** Ruled out by testing, all
with no effect whatsoever:
- panel `icon-size` at 30, 38 and 44
- the plugin's own `symbolic-icon-size` / `color-icon-size`, as both `int` and `uint`
- panel `size` (height) at 52 and 64

Meanwhile pulseaudio and power-manager icons *do* follow panel `icon-size`. Wifi
and Bluetooth therefore render through genmon `<img>` at the SVG's own size.
mintUpdate stays as an XApp icon and is accepted at 20px; it is also hidden until
there are updates (`hide-systray`).

**xapp-status-plugin holds every XApp status icon in one widget.** nm-applet and
mintupdate both register there, so they render as one contiguous group and cannot be
placed at separate positions in the bar. Within the group they are sorted by bus name
(`mintUpdate_py` before `nm_applet`), which is also not controllable. Wifi was taken
out of XApp entirely (genmon) for that reason; nm-applet is disabled.

**The systray plugin is the same kind of trap for StatusNotifier items.** Blueman and
Claude both land in plugin-8 and cannot be split. Bluetooth is therefore a genmon
indicator too, with blueman hidden via `hidden-items`.

**`xfce4-cpugraph-plugin` defaults to `in-terminal=1`.** Its click command therefore
opens inside a terminal window — this was the stray terminal appearing alongside
System Monitor. The key is `in-terminal`, not the `InTerminal` string in the binary.

**GTK3 ignores `gtk-tooltip-timeout`.** The property still exists and is readable
(value 500), but setting it changes nothing — GTK3 hardcodes the hover delay. Verified
by comparing 120 vs 2000: tooltips appeared at the same moment under both. The panel
tooltip delay is not configurable without patching GTK.

**`hide-systray` does not mean "never show the icon".** The gsettings key name is
misleading. The Update Manager preference is *"Only show a tray icon when updates are
available or in case of errors"*. With it on, mintUpdate still shows its XApp icon
whenever `set_status` is called with `visible=True` — which is the "updates available"
and "restart required" paths. A genmon replacement that assumed the stock icon would
stay gone therefore produced two icons as soon as there were updates. The setting also
does nothing to a running `mintUpdate` until that process is restarted
(`mintupdate-launcher`).

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

**Cmd+Shift+3 is not an xfconf name.** Binding `<Super><Shift>3` is a silent no-op
on this keyboard — see Screenshots above. Do not "fix" it by putting `3` back.


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

## Autostart

Login starts a set of things this machine has no use for. The pattern for turning one
off, already used for `nm-applet`, is a same-named file in `~/.config/autostart/` with
`Hidden=true` — a user override of the entry in `/etc/xdg/autostart/`. It does not
touch the package, so an update cannot undo it and `apt` never fights you for it.

| Entry | State | Why |
|---|---|---|
| `nm-applet` | disabled (pre-existing) | the bar uses [`bin/panel-wifi`](../bin/panel-wifi) genmon instead |
| `org.gnome.Evolution-alarm-notify` | **disabled 2026-09-03** | started four `evolution-data-server` processes at every login with no Evolution installed |
| `print-applet` | **disabled 2026-09-04** | 35 MB of Python watching a print queue that does not exist — `lpstat -p` has no destinations, and [`bin/service-trim`](../bin/service-trim) masks CUPS |
| `geoclue-demo-agent` | **disabled 2026-09-04** | a location agent, on a machine where nothing asks for location |

Override kept in [`config/autostart/`](../config/autostart/). `bin/doctor` checks it.

> `nm-applet`'s user entry is a **disable override, not a stray duplicate**. It looks
> like the same file twice. Do not "clean it up".

Still autostarted and left alone: `onboard` and `orca` (both exit immediately when not
needed), `blueman` (it is the BlueZ pairing agent — only its *tray icon* is hidden,
see the Bluetooth indicator above), `xiccd`, `warpinator`, `light-locker` (the screen
locker).

Takes effect at the next login; the processes already running stay until then.

## Open / not done

- ~~Wifi icon size parity~~ — **solved** by moving wifi out of xapp into genmon.
  The old symbolic icons under `~/.icons/WhiteSur-light/` are now unused by the panel
  but left in place; `icons/generate-wifi-icons.py` still regenerates them.
- ~~**Autostart cruft.**~~ **Done 2026-09-03.** Evolution's four idle processes
  disabled; `casper-md5check` masked; journal capped. See Autostart above and
  [hardware.md](hardware.md) Housekeeping.
- **Claude's tray icon** is a black XEmbed bitmap designed for a light menu bar, so it
  reads as a hole on the dark bar. User said to leave it. The real fix would be
  switching the bar to light with WhiteSur's `--black` panel-font option.
- ~~**Night light.**~~ **Done 2026-09-02.** Stock redshift-gtk rejected (size,
  placement, menu). genmon moon is plugin-23, redshift is the engine.
- ~~**Thermals / battery.**~~ **Done 2026-09-01.** Fanless; unrestricted Electron still
  82–93 °C on AC (full turbo, by design). On battery: `power-saver` +
  `max_perf_pct=70` (~77 °C / ~5.8 W package under the same load).
  [hardware.md](hardware.md) Thermals. Do not add picom.
