# Mintdrop — send a file to a machine that is nearby

> 2026-09-11. Working between Linux machines. The phone half is not built
> yet; the last section says exactly what it needs.

Pick a name, send a file, no cloud and no cable. On this machine it costs
nothing until it is used: there is no daemon, no timer and no polling — the
kernel holds a listening socket, and a process exists only while a file is
actually moving.

```
mintdrop peers                       what is nearby
mintdrop send "Studio iMac" a.pdf    send it
mintdrop status                      what is armed here
bin/mintdrop-install                 install; --revert puts it all back
```

## Four ways in

| | |
|---|---|
| **the dock** | drag files onto the Mintdrop icon in Plank |
| **Files** | right-click a selection → *Send with Mintdrop* |
| **the sheet** | `mintdrop-menu`, then drop files onto a device |
| **a terminal** | `mintdrop send` |

<p align="center">
  <img src="images/mintdrop-sheet-light.png" alt="The Mintdrop sheet, light" width="239">
  &nbsp;
  <img src="images/mintdrop-sheet-dark.png" alt="The Mintdrop sheet, dark" width="232">
</p>

The sheet is one window: round tiles for the devices that are nearby, a
glyph saying what kind of thing each one is, and the transfer drawn on the
tile itself as a ring closing clockwise from twelve. Dropping files on a tile
sends them; so does clicking one, when the sheet was opened with files
already. Escape closes it. Nothing is resident — discovery runs while the
window is open and stops when it closes.

The glyphs are drawn rather than taken from an icon theme, for the reason
`bin/bt-menu` draws its own: three shapes at one size, which then match the
appearance exactly and cannot go missing when a theme changes.

**Phones appear here already, marked *Quick Share*, and cannot be sent to
yet.** They are shown rather than hidden because a device that is genuinely
there and genuinely not ready is more useful to see than to omit — clicking
one says so.

### The right-click entry, and where it was wrong

Thunar keeps custom actions in `~/.config/Thunar/uca.xml`. The first version
of this installed a `.desktop` file into
`~/.local/share/file-manager/actions/`, which is where Nemo and Caja look and
where Thunar never does — so the entry the README promised did not exist.
`bin/mintdrop-install` now edits `uca.xml`, and:

- it **edits rather than replaces**: that file holds the user's own actions
- it is **idempotent**, keyed on the unique-id `mintbook-mintdrop`
- `--revert` **removes by that id** rather than restoring a backup, so an
  action added after the install is not silently deleted

Thunar may need `thunar -q` before the entry appears; Plank picks up its new
launcher on its own.

---

## Why this is not AirDrop, and why it is still native

This was asked for as "an airdrop". Apple's AirDrop cannot be built on this
machine, and the reason is worth writing down so nobody spends a weekend on it:

**AirDrop puts the data on AWDL**, Apple's peer-to-peer Wi-Fi link. Speaking
it on Linux means `owl`, which needs the wireless card in monitor mode *with
frame injection*. This machine's card is a **BCM4350 on `brcmfmac`** — no
injection, no monitor mode worth the name, and no nexmon firmware patch for
this chip. It is a hardware limit, not a missing library. An iPhone will not
see this machine in its AirDrop sheet, and no amount of code changes that.

**Quick Share — Samsung's and Google's — separates the two media.** BLE and
mDNS to announce and agree; then an ordinary TCP connection over the access
point both devices are already associated with. That runs on any card. It is
why Quick Share works on hardware AirDrop cannot use, and it is the shape
mintdrop follows.

So the nearby-sharing idea transfers to this machine intact. Only Apple's
particular radio trick does not.

---

## What it costs when nothing is happening

This is the part that matters on a fanless two-core machine, and it is the
reason the design looks the way it does.

| | how |
|---|---|
| receiving, idle | **no process.** `mintbook-drop.socket` is a systemd user socket; the kernel holds the listen queue and systemd starts `mintbook-drop@.service` only when a connection actually arrives |
| being discoverable | **no process.** a static file in `/etc/avahi/services`, read by the `avahi-daemon` that is already running for the rest of the system |
| discovering others | **no process between uses.** the picker runs one short `avahi-browse --terminate` while its window is open, and nothing when it is closed |
| receiving, active | one Python process, `Nice=10`, I/O scheduling class `idle`, which exits when the file has landed |

That is CONTRIBUTING rule 3 satisfied by not having a daemon, rather than by
making one cheap. Compare the alternatives that were not built: a resident
receiver would idle a process forever for a feature used twice a week, and an
`avahi-publish` advertisement would idle a second one.

The `Nice=10` and idle I/O class are deliberate. A large file arriving must
not make the desktop stutter on two cores, and the radio caps throughput long
before the scheduler does — so yielding to the foreground costs the transfer
nothing it was going to get. Same reasoning as [priority.md](priority.md).

---

## How it moves the bytes

One TCP connection per transfer:

```
->  'MNTD' 0x01  u32 header length  header (JSON: sender name, names, sizes)
<-  one byte: accept / decline / busy
->  every file's bytes, back to back, exactly `size` each, in order
<-  one byte: received
```

No per-chunk framing, which is what lets each end hand the whole run to the
kernel: `os.sendfile()` out of the page cache into the socket on the sender,
`os.splice()` out of the socket into the file on the receiver. Neither end
copies the bytes through Python.

The cost of no framing is that the declared sizes are the only boundary
between two files. They are not trusted: every read is bounded by the
remaining count, a stream that ends early fails the transfer rather than
running into the next file, and each file is written to `NAME.part` and
renamed only after its own byte count has landed exactly. A failed transfer
leaves nothing behind that looks finished.

### Measured: splice() does not beat a buffered read here

`bin/mintdrop-probe` runs both receive paths over loopback and reports MB/s
and CPU seconds per gigabyte. 2026-09-11, 384 MB per trial, 3 trials each,
payload warm in page cache:

| receive path | throughput | CPU |
|---|---|---|
| `os.splice()` | 238 MB/s | 2.60 s/GB |
| buffered read | 262 MB/s | 2.45 s/GB |

Worst within-arm spread was 76 MB/s — **larger than the difference**, so this
measured nothing except that the two paths are equivalent on this machine at
these rates. Both are far above what the radio can deliver, so neither is the
constraint. `splice()` is kept as the default because it is written and
works; `mintdrop serve --no-splice` and `mintdrop receive --no-splice` select
the buffered path, and the tests check that the two produce identical bytes.

The first version of the probe reported "not measurable" for everything
because it timed the two processes from the outside, which mostly measured
two Python interpreters starting up — about 0.6 s of CPU, larger than the
difference under test. The numbers above come from `mintdrop-stat` lines that
bracket the bulk loop only.

### Not measured: the radio

**There is no number here for a real transfer over Wi-Fi, because there is no
second machine running mintdrop to measure against.** The link negotiates
866 Mb/s on 5 GHz, and 802.11ac in practice delivers well under half of its
link rate, so expect something in the tens of MB/s rather than the hundreds
above. When a second machine exists:

```
bin/mintdrop-probe --peer "Other Machine"
```

and the number belongs in this section, labelled with its date.

---

## Accepting

A receiver that writes files to disk because a stranger asked is a bug with a
filename. So:

- **Only local addresses.** Private, link-local and loopback; anything
  routable is refused before the offer is even read. IPv4 peers arrive on the
  dual-stack socket as `::ffff:a.b.c.d` and are unwrapped first — getting
  that wrong rejected the entire LAN, and there is a test for it now.
- **Every transfer is prompted** — sender, filename, size, address — unless
  the sender's name is in `~/.config/mintbook/mintdrop.known`, which is what
  the prompt's *Always accept from…* button writes.
- **A prompt that cannot be shown is a decline**, and so is one nobody
  answers within 45 seconds. Escape declines. The default answer is no.
- **Names from the network are not paths.** Separators, control characters,
  `..` and leading dots are removed before a name touches the filesystem, and
  an existing file is never overwritten — `report (2).pdf` instead.

`~/.config/mintbook/mintdrop.conf`, all optional:

```ini
accept = ask      # ask (default) | known | off
dir    = ~/Downloads
name   = Cobo's MacBook
```

### What it does not do

**The transfer is not encrypted, and the sender is not authenticated.** A name
in the offer is a claim, and anyone on the same LAN can make it. The prompt is
the whole gate. That is fine for moving a file between your own machines on
your own network, and it is not fine on a café's Wi-Fi — there, leave
`accept = ask` (the default) and read the prompt, or `accept = off`.

TLS would fix the eavesdropping half and cost the zero-copy path, since
`sendfile()` into a TLS socket needs kernel TLS that Python does not expose.
That trade was not made here. It is the right thing to revisit alongside the
phone half below, which needs real key exchange anyway.

---

## Installing

```
bin/mintdrop-install          # scripts, user socket, Thunar entry, advert
bin/mintdrop-install --revert
```

User-level, with a persistent undo snapshot, like
[daily-install](daily.md): repository symlinks into `~/.local/bin`, the
pre-install state of every file recorded once, and a rerun that adds newly
introduced files to the original snapshot rather than replacing it.

Root is needed for exactly one file — `/etc/avahi/services/mintdrop.service`,
the advertisement — and the installer asks `sudo` for that alone.
`--no-advert` skips it: other machines then cannot *find* this one, but
sending from it, and receiving from a peer told where to look
(`mintdrop send 192.168.1.140:8771 file`), both still work.

`--revert` disarms the socket and restores every file, and prints the one
`sudo rm` for the advertisement rather than asking for root on the way out.

### The prompt needs to find the display

A socket-activated user service does not inherit `DISPLAY` from a session it
was not started by. `config/autostart/mintbook-drop-env.desktop` runs
`systemctl --user import-environment DISPLAY XAUTHORITY
DBUS_SESSION_BUS_ADDRESS` at login, and the installer runs it once
immediately so the first transfer works without logging out. If a prompt ever
fails to appear, that import is the first thing to check — the transfer will
have been declined and the journal will say
`declined: no prompt available`.

---

## Verified, 2026-09-11

On this machine, before installing anything system-wide, using
`systemd-socket-activate` in place of the real unit:

- socket activation spawns the receiver per connection and it exits after —
  the connection is found on `LISTEN_FDS`/fd 3 and on stdin, since which one
  systemd uses has moved over its life
- `accept = off` declines and writes nothing; `accept = known` accepts a
  listed sender
- 512 MB over loopback arrives byte-identical (md5), as do 4 MB and a 4-file
  run with no framing between the files
- the prompt and the picker both render in the light appearance at this
  machine's DPI; Escape declines
- `python3 -m unittest discover -s tests` — 150 tests, all passing, 19 of
  them new

Not verified: a transfer over the radio to another machine, and the picker
showing a real peer. Both need a second machine running mintdrop.

---

## The phone half — Quick Share

An unmodified Samsung or Android phone will see this machine only if it
speaks **Quick Share**. That work is in progress, in stages that can each be
tested on their own.

### Done: the phone can see this machine

`bin/mintbook_quickshare.py` builds the advertisement, and
`bin/mintdrop-install` writes it to
`/etc/avahi/services/mintdrop-quickshare.service`. It is a static file like
the mintdrop one, so being discoverable by a phone costs no process either.

Discovery is mDNS **and** BLE. An earlier version of this section said BLE
was only a nudge and not needed; that was wrong — see *Bluetooth: why mDNS
alone was not enough* below. Bluetooth must be on, or the phone will not list
this machine however correct the mDNS record is.

The layouts come from grishka's reverse-engineered
[PROTOCOL.md](https://github.com/grishka/NearDrop/blob/master/PROTOCOL.md),
and they fail silently: a wrong bit raises nothing, it just means the phone
never lists the machine. `tests/test_quickshare.py` pins every offset.

| | |
|---|---|
| service type | `_FC9F5ED42C8A._tcp`, the first three bytes of SHA-256("NearbySharing") |
| instance name | 10 bytes, base64url unpadded: `0x23`, endpoint id (4), `FC 9F 5E`, `00 00` |
| TXT `n` | `version<<5 \| hidden<<4 \| type<<1`, 16 identity bytes, name length, name |
| port | 8771 — the socket mintdrop already listens on |

Two details worth keeping:

- **The endpoint id is stored**, in `~/.local/state/mintbook/quickshare-endpoint`.
  Regenerating it each boot would show up on the phone as a new device every
  time.
- **The 16 identity bytes are random.** They encode a Google account for
  "Contacts" visibility, and this machine has no account, so the phone cannot
  place it as a contact and lists it under Everyone — which is the right
  visibility for a laptop anyway.

One listener serves both protocols. `bin/mintdrop` reads four bytes before
deciding anything: `MNTD` is mintdrop, and anything else is a protobuf length
and belongs to Quick Share. So the phone connects to the same socket unit,
and the idle cost does not double.

### Bluetooth: why mDNS alone was not enough

**Retracted, 2026-09-12.** This doc previously said discovery was mDNS and
that "BLE is only a nudge, so it is not needed for a phone on the same
Wi-Fi". That was wrong, and the phone proved it: the advertisement was live
and structurally identical to the phone's own, and the phone still never
listed the machine.

Android sleeps its Nearby stack to save battery, and a sleeping phone does
not look at the network. A BLE advertisement carrying `0000fe2c` is what
wakes it. rquickshare carries one for the same reason, and says plainly that
without Bluetooth a phone often never lists the Linux machine at all.

So Bluetooth is **required** for a phone to find this machine, and the
machine had it rfkill soft-blocked — which is a fine way to run a laptop, and
means Quick Share cannot work until it is on.

#### The payload was measured, not guessed

Nothing documents the service data. With Bluetooth on, a real Quick Share
device a metre away broadcasts:

```
FE2C service data = 00 40 10 2a 05 00 11 5d      (8 bytes, 2026-09-12)
```

`bin/mintbook_ble.py` advertises the same shape — a zero version byte and
seven identifying bytes — with its own random tail. Copying those bytes
verbatim would be claiming to be that phone. **What the seven bytes mean is
still unknown**, and if a phone sees the machine but refuses to talk to it,
this is the first thing to suspect.

#### Two things BlueZ will not tell you

- `RegisterAdvertisement` calls back into the caller for the advertisement's
  properties *before* it replies. Call it synchronously and it deadlocks
  against the loop that would serve that callback, then fails with
  `Did not receive a reply`.
- It rejects the whole advertisement with `Failed to parse advertisement`,
  naming no field, unless the service data is `dbus.Byte` elements and
  `Discoverable`/`IncludeTxPower` are absent. Found by trying variants and
  watching which registered.

#### It is the one resident thing here, and it is time-boxed

A BLE advertisement lives exactly as long as the D-Bus connection that
registered it. So visibility costs a process for as long as you asked for and
not a second longer:

```
mintdrop visible 120     # findable by a phone for two minutes
```

and the sheet holds one for exactly as long as it is open. Nothing advertises
in the background. A laptop that broadcasts its presence all day to save two
seconds of waiting is the trade this deliberately does not make.

### Not done: the conversation

Being listed is not being able to receive. Still to build, on that same
connection:

1. length-prefixed protobuf framing (4-byte big-endian) and `OfflineFrame`
2. the UKEY2 handshake — P-256 ECDH, HKDF-SHA256 with the two fixed salts
3. the D2D secure-message layer — AES-256-CBC plus HMAC-SHA256, sequence
   numbered
4. the sharing frames — paired-key encryption, the introduction listing the
   files, accept/reject, then chunked `PAYLOAD_TRANSFER`
5. `KEEP_ALIVE` every 10 seconds, which Android expects both ways

The plan is to hand-roll a small protobuf codec rather than add a dependency:
the wire format is varints and length-delimited fields, only a handful of
messages are needed, and this machine does not need a package installed to
move a file. The accept prompt, the download directory and the name handling
are already shared, in `bin/mintbook_drop.py`, so Quick Share arrives as an
adapter beside mintdrop rather than as a second copy of everything.

Reference implementations to read when stuck: `grishka/NearDrop` (macOS,
Swift), `teaishealthy/pyquickshare` (Linux, Python).
