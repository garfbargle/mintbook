# Display — HiDPI scaling

The panel is **2304x1440 in 259x162mm**, which is **~226 real DPI** — genuine Retina
density, comparable to a MacBook Pro. At stock settings every UI element is drawn at
native pixel size, so a fresh install is close to unreadable.

## Current values

| Setting | Value | Effect |
|---|---|---|
| `xsettings /Gdk/WindowScalingFactor` | **1** | window/widget scale |
| `xsettings /Xft/DPI` | **168** | font scale (1.75x of the 96 baseline) |
| `xsettings /Gtk/CursorThemeSize` | **40** | pointer size |
| `xfce4-panel /panels/panel-1/size` | **52** | bar height |
| `xfce4-panel /panels/panel-1/icon-size` | **36** | bar icons |

```bash
xfconf-query -c xsettings    -p /Xft/DPI -s 168
xfconf-query -c xsettings    -p /Gdk/WindowScalingFactor -s 1
xfconf-query -c xsettings    -p /Gtk/CursorThemeSize -s 40
xfconf-query -c xfce4-panel  -p /panels/panel-1/size -s 52
xfconf-query -c xfce4-panel  -p /panels/panel-1/icon-size -s 36
```

All of these apply **immediately**. No logout, no restart.

> Creating `/Xft/DPI` for the first time needs an explicit type:
> `xfconf-query -c xsettings -p /Xft/DPI -n -t int -s 168`.

---

## Why it is split this way

**XFCE only does integer window scaling.** `Gdk/WindowScalingFactor` can be 1 or 2 —
there is no 1.5. On this panel:

- **2x was far too large.** Everything doubled in physical size; unusable.
- **1x with default 96 DPI is far too small.** The starting state.

So the working configuration is `WindowScalingFactor=1` with `Xft/DPI` raised to get a
fractional-feeling result. **Only fonts scale.** Every pixel-sized icon still renders
at raw size, which is why icons must be enlarged individually and why the bar and
cursor have their own explicit sizes above.

DPI was tuned by eye in stages: 96 (too small) → 144 (still too small) → **168**
(accepted). 192 is the true 2x-equivalent and was rejected as too large.

## If you change the scale

- **`Gtk/CursorThemeSize` and the panel sizes do not follow DPI.** Scale them by hand
  or the pointer and bar will look wrong against the new text size.
- **`xfwm4 /general/margin_top` must equal the panel height.** The panel sets no
  struts on this system, so that margin is the only thing keeping maximized windows
  from rendering under the bar. See [desktop.md](desktop.md).
- Some applications keep their own scaling and will not follow xsettings — **Firefox**
  (`layout.css.devPixelsPerPx`) and **Electron apps** in particular.

## Screenshots

`xfce4-screenshooter` is the only screenshot tool installed (no `scrot`, `maim`, or
`import`). This keyboard has **no Print key** — use the Super (Cmd) chords in
[desktop.md](desktop.md). Files land in `~/Pictures/Screenshots/`:

```
Cmd+Shift+3   fullscreen
Cmd+Shift+4   region
Cmd+Shift+5   window
```

A 160ms full-screen white flash follows a successful save (not in the PNG).
Do not bind `<Super><Shift>3` in xfconf; XFCE looks up `numbersign` /
`dollar` / `percent`. Do not pass `-s` a directory. See [desktop.md](desktop.md).

From a terminal, to check scaling:

```bash
xfce4-screenshooter --fullscreen --save /tmp/screen.png
```
