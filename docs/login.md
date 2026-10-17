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

### Two ways in, and what to re-run

`Ctrl+Cmd+Q` locks and `Cmd+Shift+Q` logs out — both land here. They are
installed by [`bin/daily-install`](../bin/daily-install); the logout one goes
through a wrapper for a reason worth reading before binding anything else to a
dialog, in [desktop.md](desktop.md#gotchas--things-that-cost-real-time).

**Re-run `sudo bin/login-install` after pulling changes to any of these.** The
installer copies rather than links the privileged half, so an edit to
`bin/login-apply` in a checkout changes nothing on the machine until it is
installed again — and a machine running an older copy of it looks exactly like
a machine where the newer behaviour does not work. That is how the dconf fix
came to be tested against an installed helper that predated it.

| changed | needs |
|---|---|
| `config/lightdm/slick-greeter.conf`, `greeter.css` | `sudo bin/login-install` |
| `bin/login-apply`, the polkit files | `sudo bin/login-install` |
| `bin/login-settings`, `bin/wallpaper-mode` | `sudo bin/login-install` (installs them into `~/.local/bin`) |
| `bin/session-logout`, the shortcuts | `bin/daily-install` |
| the theme in `~/.themes` | `sudo bin/login-install`, which re-copies it |

---

## Choosing the picture

<!-- A screenshot belongs here. See "No screenshot in this repository" below. -->

The background lives in a root-owned file, and the greeter reads it as a user
that cannot enter your home directory. Both halves of that are real, and
neither is anybody's business but this program's:

| | |
|---|---|
| [`bin/login-settings`](../bin/login-settings) | The window. Cairo on the popup glass with soft multi-ring drop shadow, specular rim, header drag, hover states, and smooth scroll, managed by `bin/palette-generate` |
| [`bin/login-apply`](../bin/login-apply) | The root half, installed as `/usr/local/sbin/mintbook-login-apply` |
| [`config/polkit/org.mintbook.login.policy`](../config/polkit/org.mintbook.login.policy) | The action pkexec authorises, by path |
| [`config/polkit/10-mintbook-login.rules`](../config/polkit/10-mintbook-login.rules) | Admin, local, active — no password on every click |

Every change also writes the same values into **lightdm's own dconf**, because
the file by itself does not decide what you see — see the race below.

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

### One pair, both surfaces

**Reversed on 2026-09-14.** Earlier the same day this section said the login
screen deliberately did *not* follow the desktop, and the reasoning was that
linking them meant watching a user setting in order to make a privileged call.
That reasoning was wrong about the cost, for a reason the first design hid: the
greeter has a single `background` key, so choosing Dark in the window kept the
light picture and swapped only the theme. Once the answer is a *pair* rather
than a picture, there is already a moment when the pair changes —
[`bin/appearance-mode`](../bin/appearance-mode), which switches the chrome at
Redshift's sunset boundary — and nothing needs watching at all.

[`bin/wallpaper-mode`](../bin/wallpaper-mode) owns the rule:

```
wallpaper-mode light|dark         # apply the stored picture for that mode
wallpaper-mode --set dark PATH    # store it, and apply if that mode is live
wallpaper-mode --check
```

Two paths in `~/.config/mintbook/wallpaper.light` and `.dark`. On a change,
the desktop gets it across every monitor and workspace xfconf knows about —
the property list is read rather than assumed, because it differs per monitor
and outlives the display that created it — and the login screen gets it,
with the matching appearance, through pkexec.

The privileged call happens at sunset and sunrise, not on every panel tick:
`appearance-mode` returns early when the mode it is asked for is already
applied, so this hook only ever runs on a real change. It also compares against
the picture last *asked* for rather than what the conf says, because a picture
from your home is copied into `/usr/share` and the conf names the copy.

Setting the half you are not currently in changes nothing on screen until that
time of day comes, which is what makes it safe to choose a dark picture at
noon.

### Which pictures pair

Measured on **2026-09-14**: mean luminance of every wallpaper in
`/usr/share/backgrounds/linuxmint-wallpapers`, thumbnailed and converted to
grey. The window offers four, each one photographer's own light and dark
picture so the two halves look like the same machine at two times of day.

| pair | light | | dark | |
|---|---|---|---|---|
| Silver | `mfakurian_silver` | 193 | `mfakurian_order` | 21 |
| Gold | `jpanchal_gold` | 163 | `jpanchal_waves` | 28 |
| Sweets | `rapciu_sweets` | 188 | `rapciu_pearl` | 91 |
| Snow | `sjohnson_snow` | 104 | `sjohnson_sphere` | 50 |

The extremes of the set, for choosing by hand: `pczerwinski_pink` 194 and
`mfakurian_silver` 193 at the light end, `porioni_dark` 10 and
`mfakurian_order` 21 at the dark end. Luminance is a mean over the whole frame
and says nothing about where the bright part *is*, which is what decides
whether a white login card is readable on it.

**Not done: the interim pictures.** macOS moves through a series across the
day, not two states. This has two, switched at the same boundary the chrome
uses.

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
- **`content-align=center` was claimed confirmed on 2026-09-14. It was not.**
  The nested preview centres the card, but the preview seeds dconf before it
  starts and the real greeter does not: on the real login screen the card
  stayed left, on a conf that plainly says `center`. Same race as the preview's
  — the greeter copies the conf into dconf and reads it straight back, and
  lightdm's dconf already held the schema default from every start before any
  of this existed. Fixed by writing the values into lightdm's dconf too; the
  claim stands or falls on the next lock, not on a preview.
- **Apply has not been run end to end.** The window, the helper's validation,
  its copy-and-prune and its conf rewriting were each exercised; the pkexec
  path and the polkit rule cannot be tested without installing them, which
  needs root. First run is the first test.
- **No screenshot in this repository.** `Cmd+Shift+3` is a session binding and
  the greeter is not the session. `--preview --shot` is how to take one.

### 2026-10-08: privileged-helper safety

Wallpaper paths are written as literal configuration values, including shell and
sed metacharacters. Newlines in paths are rejected. Dconf is written through
Gio with typed values in one lightdm D-Bus session; no configuration value is
executed as shell source. A private picture is copied as the invoking user.
Missing appearance assets now require the authenticated `login-install` rather
than copying a user-controlled theme tree through the passwordless helper.
Reinstall with `sudo bin/login-install` after the README Timeshift snapshot.
The installer's existing `--revert` restores the original login setup.

For an existing installation, `sudo bin/safety-install` deploys the reviewed
helper fixes with targeted root-file backups (no Timeshift/rsync by default); afterward run
`bin/input-boost-install` as the desktop user. See
[the top-bar review](top-bar-review.md) for deployment status and undo details.
