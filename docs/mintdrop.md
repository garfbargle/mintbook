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
mintdrop send --pick a.pdf           choose in the picker
mintdrop status                      what is armed here
bin/mintdrop-install                 install; --revert puts it all back
```

In Files, right-click one or more files and choose **Send with Mintdrop**.

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

## The phone half

An unmodified Samsung or Android phone will see this machine only if it
speaks **Quick Share**, which means, on the same listener and the same
`_mintdrop._tcp`-shaped discovery:

- BLE advertisement of the Quick Share service UUID. BlueZ on this machine
  exposes `LEAdvertisingManager1` on hci0, so the radio side is available.
- Google's Offline Wire Protocol: protobuf framing, a Ukey2 handshake, and
  AES over the resulting session key. `python3-protobuf` is in the archive;
  `cryptography` is already installed.

`bin/mintdrop`'s listener reads four bytes before deciding anything and
dispatches on them, so a second protocol is an adapter beside the first
rather than a rewrite — that is why discovery, the accept prompt and the
receive loop live in `bin/mintbook_drop.py` instead of inside the mintdrop
wire format. The existing Linux implementation to read first is
`rquickshare`; nothing here needs to be invented from scratch.

This is a real protocol implementation, not an afternoon, and it is not
started.
