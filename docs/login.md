# Login — the greeter, in the desktop's own chrome

Everything else on this machine got looked at. The login screen did not: it was
still Mint-Y-Aqua, Ubuntu 11, a hostname, a keyboard indicator, and a 24-pixel
cursor that jumped to 40 the moment the session started.

It is also not once a day. `light-locker` hands the lock screen to the same
binary, so this is the surface between you and the machine every time the lid
opens.

```
bin/login-install --check              # what is set now, and what is in the way
bin/login-install --preview            # the real greeter, in a nested X server
bin/login-install --preview --dark
sudo bin/login-install                 # install (light)
sudo bin/login-install --dark
sudo bin/login-install --revert
```

Once it is installed, the picture is chosen in a window — **Login Screen**, in
the app grid and in Overview, or `login-settings` — not by editing anything.

Nothing restarts and nobody is logged out. The greeter reads its file when it
starts, so the next lock is the next time you see it.

Two files do the work.
[`config/lightdm/slick-greeter.conf`](../config/lightdm/slick-greeter.conf) is
the greeter's own settings, and
[`config/lightdm/greeter.css`](../config/lightdm/greeter.css) is the half those
settings cannot reach.

---

## Choosing the picture

<!-- A screenshot belongs here. See "No screenshot in this repository" below. -->

The background lives in a root-owned file, and the greeter reads it as a user
that cannot enter your home directory. Both halves of that are real, and
neither is anybody's business but this program's:

| | |
|---|---|
| [`bin/login-settings`](../bin/login-settings) | The window. Cairo on the popup glass, like Control Center |
| [`bin/login-apply`](../bin/login-apply) | The root half, installed as `/usr/local/sbin/mintbook-login-apply` |
| [`config/polkit/org.mintbook.login.policy`](../config/polkit/org.mintbook.login.policy) | The action pkexec authorises, by path |
| [`config/polkit/10-mintbook-login.rules`](../config/polkit/10-mintbook-login.rules) | Admin, local, active — no password on every click |

It offers the wallpaper the desktop is showing, the forty-nine Mint wallpapers
and the XFCE ones already on the disk, anything in `~/Pictures`, and a file
chooser first in the grid rather than last.

**A picture in your home is copied.** The greeter cannot read one where it
lies, so `mintbook-login-apply` puts it under `/usr/share/mintbook/backgrounds`
and points the greeter there — pruning the copy it replaces. It is a copy with
everything that implies: edit the original afterwards and the login screen
keeps the version it was given. `--revert` takes the copies back.

Asking for Dark having installed Light fetches the dark theme pair too, rather
than bottoming out in "now go and run this in a terminal".

### It does not follow the desktop wallpaper

Decided on **2026-09-14**, deliberately. Changing the wallpaper in XFCE's
Desktop settings changes the session desktop and nothing else; the login screen
keeps its own picture until you change it in the window. They start out
matching, because the installer reads xfconf once, and they drift from there.

Linking them would mean something watching a user setting in order to make a
privileged call, plus that copy into `/usr/share` on every change, for a
surface you look at for four seconds. Two settings, each changed where you
would look for it, is the cheaper arrangement.

---

## What changed

| | was | is |
|---|---|---|
| GTK theme | Mint-Y-Aqua | WhiteSur-Light — the session's |
| icons | Mint-Y-Sand | WhiteSur-light |
| cursor | Bibata at 24 | Bibata at 40, which is what the session runs |
| backdrop | Mint's default wallpaper | the wallpaper xfconf actually has |
| before the wallpaper | `#000000` | Pearl `#e5e7ea`, from the glass palette |
| alignment | left | centred |
| menubar | hostname, keyboard, a11y, power, clock, quit | a11y, power, clock |
| clock | `%H:%M` | `%a %-d %b  %H:%M`, the top bar's own format |
| user list and prompt | the greeter's size | 23px Inter, the session's size |

The accessibility menu stays. Removing it is not minimalism, it is a lockout.

`--dark` swaps the theme pair and the backdrop colour for the slate side of
[`config/theme/mintbook-glass.ini`](../config/theme/mintbook-glass.ini). It is
chosen at install time and stays chosen — see *Open* below.

---

## What the settings file can and cannot reach

**2026-09-13**, slick-greeter 2.2.6+zena, measured by running the real greeter
against a candidate file in a nested X server and diffing the frames.

| key | effect |
|---|---|
| `theme-name`, `icon-theme-name`, `cursor-theme-size` | applied, and the greeter logs each one |
| `background`, `background-color` | applied |
| `show-hostname`, `show-keyboard`, `show-quit`, `clock-format` | applied |
| `font-name` | **the menubar only.** The user list and the password prompt do not move |
| `xft-dpi` | **nothing.** 96, 168 and 250 render pixel-identical frames |
| `content-align` | **unverified** — see the limits below |

`font-name` and `xft-dpi` stay in the file anyway. They are correct, they cost
nothing, and a later version may start honouring them.

Limits of the measurement, which are not small:

- Test mode invents its own monitor geometry — 800×600 and 640×480 — so the
  login box sits where that puts it and the wallpaper is scaled to it. Nothing
  about **layout** at 2304×1440 was measured, which is exactly what
  `content-align` is.
- The preview runs as you, so it can read a theme out of `~/.themes` that the
  real greeter could not. `--check` is what answers that question.
- Frames were diffed at 900×700 in a nested server, not photographed off the
  panel.

## The stylesheet, and why there is one

The two things you actually look at — your name and the password box — take
their size from neither `font-name` nor `xft-dpi`. On a 226 dpi panel that
leaves them at a size drawn for a much older screen.

GTK reads a user stylesheet at a higher priority than an application's own
provider, and the greeter's home is `/var/lib/lightdm`. So
`/var/lib/lightdm/.config/gtk-3.0/gtk.css` reaches what the settings file
cannot:

```css
.lightdm, .lightdm * {
  font-family: Inter, sans-serif;
  font-size: 23px;
}
```

`.lightdm` is the greeter's top-level window. The descendant half is not
decoration: setting the size on the window alone moved the menubar and left the
user list and the prompt exactly where they were, because they carry a font of
their own for inheritance to lose to.

23px is Inter 10 at the 168 dpi this desktop runs — device pixels on purpose,
because `pt` would be resolved against the greeter's idea of the screen's dpi,
and that is the broken quantity. **If the desktop's Xft DPI changes, this
number changes with it.** Nothing enforces that.

One cost, seen in the preview: the login card has a fixed width, so a very long
full name clips sooner at 23px than it did at the default size.

## What the login card is not

The dark glass card is drawn by slick-greeter itself, not by the GTK theme.
Under a stylesheet that washed the entire window green, the card stayed a
darker patch of its own. It does not become Pearl, and the theme swap shows up
in the password entry, the menubar widgets and the font rather than in the card.

A stylesheet keyed to the greeter's private widget tree could probably chase it
further. That is a re-skin that breaks on the next slick-greeter release, for a
surface you look at for four seconds. Deliberately not done.

## Two things the greeter cannot read

The greeter runs as the `lightdm` user, and `/home/cobo` is `0750`.

**The themes.** `~/.themes/WhiteSur-Light` and `~/.icons/WhiteSur-light` are
invisible to it, and a symlink into a home it cannot enter is no better, so the
installer copies both into `/usr/share`. That copy is a duplicate that does not
follow the original: update the theme in your home and the login screen keeps
the old one until `login-install` is run again. `--check` reports which
directories it owns, and `--revert` removes exactly those.

**The wallpaper.** The desktop's is under `/usr/share`, so it works. One kept
in `~/Pictures` would not, and the installer tests it as `lightdm` before
writing it — when it fails, it says so and leaves the flat Pearl instead.

## Previewing without root

`--preview` runs **lightdm itself** in its test mode on a nested display: one
monitor, the real user list, the real layout at 2304x1440. It is unprivileged,
with its own run, log and cache directories, and `/etc/lightdm` replaced inside
a `bwrap` mount namespace, so the real one is never written.

`--shot file.png` grabs the frame instead of waiting.

**Do not type into it.** While its window has focus the nested greeter grabs
the keyboard, and its password box is a real PAM conversation for your account.

Three things this got wrong first, all of them now in the code:

- **`slick-greeter --test-mode` is a trap.** It invents two monitors (800x600
  and 640x480) and a list of fixture users — *Color Background*, *Has
  Password*, *Long name (far far too long to fit)* — so it produces a cramped,
  split screen that tells you nothing. Every "limit" this document used to
  claim about layout was a limit of that, not of the greeter.
- **`bwrap` without `--die-with-parent` is not the parent of what it starts.**
  Killing it left lightdm and Xephyr running; the next run found the display
  taken and quietly moved to the next one, while the capture kept photographing
  the first session. Previews piled up on screen to be closed by hand, and two
  "captures" were byte-identical re-photographs. Hence the PID namespace, the
  process group, the display number read from the log, and a teardown that
  checks whether the display still answers — `SIGKILL` leaves both the socket
  and the lock file behind, and a stale lock stops the next run dead.
- **The greeter does not read its settings from the file.** It copies them into
  dconf and reads them back; the write goes over D-Bus and the read comes
  straight off the mapped database, so the read can win and the frame shows
  whatever dconf already held. Three captures in a row came out identical and
  wrong that way. The values now go into both places, and your dconf is put
  back afterwards.

## Open / not done

- **The appearance mode does not follow.** `bin/appearance-mode` switches the
  session between pearl and slate on a timer; the greeter's file is root-owned
  and read once at startup, so following it would mean a root-owned helper
  watching a user file. Structure for a surface you see for four seconds. The
  greeter is whichever side you installed.
- **`content-align=center` is confirmed**, as of 2026-09-14: the real greeter,
  nested at 2304x1440, centres the card. The earlier "unverified" note was a
  limit of the fixture preview, which has been replaced.
- **Apply has not been run end to end.** The window, the helper's validation,
  its copy-and-prune and its conf rewriting were each exercised; the pkexec
  path and the polkit rule cannot be tested without installing them, which
  needs root. First run is the first test.
- **No screenshot in this repository.** `Cmd+Shift+3` is a session binding and
  the greeter is not the session. `--preview --shot` is how to take one.
