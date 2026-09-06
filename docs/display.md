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
- Some applications keep their own scaling and will not follow xsettings —
  **Electron apps** in particular.
  **Chrome does follow it**: a `chrome://gpu` export reports `scale=1.75` and a
  1317x823 work area, which is 168/96 and 2304x1440 divided by it. Verified 2026-09-04.
- **Firefox follows it too — corrected 2026-09-06.** This list used to name Firefox
  as needing `layout.css.devPixelsPerPx` by hand. Firefox 155 does not: a profile
  with **no prefs at all** reports `devicePixelRatio` **1.765** and a 1306-CSS-pixel
  screen, which is 2304 physical divided by it. That is 0.8% off the desktop's
  1.75 and not visible. **Do not set `layout.css.devPixelsPerPx`** — setting it
  would pin Firefox to a fixed ratio and break it the next time the panel or the
  DPI changes. The old advice predates this Firefox.

## Video decode

The GPU is Gen8 Broadwell and libva auto-selects the Gen9+ `iHD` driver, which on this
part has no encode entrypoint at all. `i965` is the right driver here and is forced via
`/etc/X11/Xsession.d/56mintbook-libva` — see [hardware.md](hardware.md) Graphics / VA-API.
It was previously forced only via `/etc/environment.d/`, which the desktop never
reads; that is why `doctor` reported `iHD` for so long.

Neither driver decodes **VP9 or AV1**; Broadwell has no such silicon. Sites that
default to those codecs still decode on the CPU, and this chip is fanless, so that is
felt as heat rather than as dropped frames.

Chrome's own `chrome://gpu` confirms this from the other side: its hardware decode list
is h264 baseline/main/high and vp8, and nothing else. **That list is a capability
claim, not behaviour** — measured 2026-09-06, Chrome decodes in software here
regardless. See [video.md](video.md). Decode was **already hardware
accelerated before** the driver change — see [hardware.md](hardware.md), What Chrome
actually does. Encode was not.

Re-checked 2026-09-06 with i965 confirmed live in Chrome's GPU process: the decode
list is **identical**, and encode is **still software-only** under every flag tried,
including `--ignore-gpu-blocklist`. That closes the question the earlier session left
open — it is Chrome's gate, not the driver. See [hardware.md](hardware.md),
Encode with i965 live. **The only remaining playback lever is still codec selection:
getting sites to serve H.264 instead of VP9/AV1. That has not been measured here.**

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
