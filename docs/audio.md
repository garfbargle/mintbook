# Audio — internal speakers

**Status: WORKING on 7.0.** Confirmed 2026-09-01 on 7.0.0-30-generic with
[thomas-shirley/macbook8.1-speaker-driver](https://github.com/thomas-shirley/macbook8.1-speaker-driver)
(`macbook12-audio/0.1` DKMS). `coef 0x1f = 0` (clock locked). Play through
**MacBook Speaker (EQ)** (`input.MacBook_Speaker`) — Chrome/YouTube included.
Headphone jack auto-switch uses [`bin/mb81-jack-switch`](../bin/mb81-jack-switch)
(overrides the upstream unit). Kernel 6.14 is a boot fallback only — no speaker
DKMS there.

---

## Symptom

No sound from the built-in speakers, ever. The 3.5mm headphone jack works normally.
The card, the mixer and PipeWire all look completely healthy — which is the trap.

---

## The hardware, as the codec actually reports it

Run [`bin/audio-diag`](../bin/audio-diag) to regenerate all of this.

| | |
|---|---|
| Codec | Cirrus Logic **CS4208** |
| Vendor / Subsystem ID | `0x10134208` / `0x106b6400` |
| Revision | `0x100401` |
| PCI SSID seen by the quirk table | `106b:0000` (Apple) |
| Audio controller | PCI **`00:1b.0`** (Broadwell-U, Wildcat Point-LP) |

### The two output paths are not alike

```
speakers    converter 0x0a  ──digital──▶  pin 0x1d   (no amp on the pin)
headphones  DAC       0x02  ──analog───▶  pin 0x10   (Stereo Amp-Out, jack detect)
```

Pin `0x1d` — the internal speaker:

```
Node 0x1d [Pin Complex] wcaps 0x406301: 8-Channels Digital
  Pincap 0x00000010: OUT                      <- OUT only. no amp, no volume.
  Pin Default 0x901600f0: [Fixed] Speaker at Int N/A
    Conn = Digital
  Connection: 1
     0x0a
```

Converter `0x0a` that feeds it is an **`Audio Output ... Digital`** widget sitting in
power state `D3`.

**This is the whole problem.** The internal speakers are not driven by any of the
codec's analog DACs. They are fed over a digital link to a *separate amplifier chip*,
and the mainline `snd_hda_codec_cirrus` / `cs420x` driver does not know how to
initialise that amplifier. Nothing in ALSA/PipeWire configuration can substitute for
that initialisation.

Supporting evidence:

- The codec has six GPIOs (`GPIO: io=6, o=2, i=0`). **Mainline already drives GPIO 0**
  — `cs4208_fixup_mac()` falls back to `codec->fixup_id = CS4208_GPIO0` for any Apple
  CS4208 — so a stock 6.14 boot shows `IO[0]: enable=1, dir=1, data=1` on its own.
  Asserting GPIO 0 is therefore **not** the missing piece.
- At boot the driver logs `CS4208: picked fixup  for codec SSID 106b:0000` — note the
  **blank fixup name**. There is no mainline quirk for this machine.
- There is **no amplifier on any I2C bus** (`/sys/bus/i2c/devices/` holds only the
  SMBus controller and the i915 display buses), so the amp is not a separately
  driveable I2C device — it hangs off the codec.

### Stock autoconfig

```
autoconfig for CS4208: line_outs=1 (0x1d/...) type:speaker
   speaker_outs=0
   hp_outs=1 (0x10/...)
   inputs: Mic=0x18, Internal Mic=0x19
```

Analog converters present: `0x02 0x03 0x04 0x05`. Digital: `0x0a 0x0b 0x0e`.

---

## What was tried and ruled out

Each of these is **conclusively** eliminated — do not spend time on them again.

### 1. Mute / volume — ruled out

`Master`, `PCM`, `Front`, `Surround`, `Center`, `LFE`, `Side` were all already at 100%
and unmuted. `Headphone` was muted; unmuting it changed nothing. PipeWire's sink was
present, unmuted, and raised to 85%. Still silent.

### 2. Kernel `model=` quirks — ruled out

The only valid CS4208 quirks are `auto`, `gpio0`, `mba6`, `mbp11`, `macmini`
(kernel.org HD-audio models doc). `gpio0` ("enable GPIO 0 amp") is the only one that
even targets the right mechanism.

```bash
# temporary, memory-only test - a reboot reverts it
systemctl --user stop wireplumber pipewire-pulse pipewire filter-chain
systemctl --user stop pipewire.socket pipewire-pulse.socket
sudo modprobe -r snd_hda_intel
sudo modprobe snd_hda_intel model=gpio0
```

Result: the quirk *did* apply — the parse changed from `line_outs=1` to
`line_outs=5 (0x11/0x12/0x13/0x14/0x1d)` and a Digital PCM device appeared. Silent
anyway.

> **Unexplained:** the GPIO dump taken during that test read `enable=0` on all six,
> which contradicts both `model=gpio0` and the mainline Apple default. A later stock
> 6.14 boot clearly shows `IO[0]: enable=1`. Treat that one early reading as suspect
> rather than as evidence; re-measure with `bin/codec-snapshot` before relying on it.

> The services **and their sockets** must be stopped, or systemd socket-activation
> restarts PipeWire mid-unload and `modprobe -r` fails with `Module is in use`.
> Check with `fuser -v /dev/snd/*` before unloading.

### 3. Channel routing / surround profile — ruled out

Under `model=gpio0` the generic parser maps speaker pin `0x1d` as the **5th** line-out
(the "Side" channel), while the stereo profile only feeds "Front". So this was worth
testing:

```bash
pactl set-card-profile alsa_card.pci-0000_00_1b.0 output:analog-surround-51
speaker-test -D default -c6 -twav -l1
```

All six channels silent. Routing is not the problem.

> `speaker-test -D pulse` fails with `Unknown PCM pulse` on PipeWire — use
> `-D default`. `-D hw:PCH,0` returns `Device or resource busy` while PipeWire holds
> the card; that is expected, not a fault.

### 4. "MacBook8,1 is not supported" — ruled out as a *claim*

[`leifliddy/macbook12-audio-driver`](https://github.com/leifliddy/macbook12-audio-driver)
is an out-of-tree driver that replays the macOS init sequence for exactly this
speaker topology. Its README says it supports MacBook9,1 and 10,1 and explicitly
**not** MacBook8,1.

That statement is **documentation, not code**. Reading the source:

- `cs4208_probe()` calls `setup_a1534()` and `play_a1534()` **unconditionally** — no
  DMI check, no SSID gate, no revision test.
- The codec table binds on `HDA_CODEC_ENTRY(0x10134208, "CS4208", ...)`, which is this
  machine's codec.
- `SND_PCI_QUIRK_VENDOR(0x106b, "Apple", CS4208_MAC_AUTO)` is a vendor-wide wildcard.
- `patch_cirrus_a1534_setup.h` is a pure verb replay with no conditionals.
- **A1534** is Apple's chassis number for the 12-inch MacBook, which covers the 8,1
  as well as the 9,1 and 10,1.
- Its README describes the hardware it drives as converter `0x0a` → pin `0x1d` with a
  GPIO-enabled amp, and headphones on `0x02` → `0x10` — an **exact** match for this
  machine.

So it is worth trying. It just does not work yet — see below.

---

## The out-of-tree driver: current blocker

### It builds and installs fine

Prerequisites were already present (`dkms`, `gcc`, `make`, `git`,
`linux-headers-$(uname -r)`). **Secure Boot is not supported on this machine**, so
unsigned DKMS modules load without any signing step.

```bash
git clone https://github.com/leifliddy/macbook12-audio-driver.git
cd macbook12-audio-driver
sudo ./install.cirrus.driver.sh -i     # uninstall: -u
```

### On kernel 7.0 it panics at probe

```
UBSAN: array-index-out-of-bounds in sound/hda/codecs/generic.c:1507:19
index 18 is out of range for type 'auto_pin_cfg_item [18]'
...
BUG: unable to handle page fault for address: 000000020000000a
Oops: 0002 [#1] SMP PTI
RIP: 0010:cs_4208_build_pcms_explicit+0xd9/0x1d0 [snd_hda_codec_cs420x]
```

The analog card disappears entirely — **including the headphone jack**, so this is
strictly worse than stock until uninstalled.

The same panic happens if [thomas-shirley/macbook8.1-speaker-driver](https://github.com/thomas-shirley/macbook8.1-speaker-driver)
is built against kernel.org HDA headers. The working 7.0 install uses Ubuntu's
`linux-hwe-7.0` `sound/hda` tree instead. See [What actually works](#what-actually-works).

**This is memory corruption, not a logic bug.** The evidence:

1. The parse prints `inputs: Mic=0x18, Internal Mic=0x19` — `num_inputs` is **2**.
2. Moments later, inside the same parse, `count_multiio_pins()` iterates
   `for (i = 0; i < cfg->num_inputs; i++)` and reaches `i == 18`, so the kernel is now
   reading `num_inputs` as **19+**. Something overwrote the spec struct in between.
3. The oops that follows is downstream of the same corruption: in 7.0,
   `snd_hda_gen_build_pcms()` only assigns `spec->pcm_rec[0] = info` on the analog
   path. The driver then reads `pcm_rec[0]`, its `if (!info)` check passes because the
   value is *garbage rather than NULL*, and it writes into it.

`AUTO_CFG_MAX_INS` is `18` in both upstream v7.0 and the Ubuntu build, so the array
bound itself is **not** the mismatch.

**Most likely cause:** `prepare.cirrus.driver.sh` downloads **kernel.org upstream**
source and compiles the codec against those struct definitions, but the module then
loads into Ubuntu's **`linux-hwe-7.0`** kernel (the oops trace shows the build path
`/build/linux-hwe-7.0-qG208a/...`). Wherever those two disagree on a field in
`struct hda_gen_spec`, every write the driver makes lands at the wrong offset. 9,1 and
10,1 owners never hit this because their kernels happened to agree with upstream.

### On kernel 6.14 it loads, and the speakers stay silent

The 6.14 build uses a *different, older and better-tested* code path
(`patch_cirrus.c` → `snd-hda-codec-cirrus`, versus `cs420x.c` for kernels >= 6.17).
It failed to build only because of a transient kernel.org HTTP/2 download error:

```
Downloading linux-6.14.tar.xz
curl: (92) HTTP/2 stream 1 was not closed cleanly: PROTOCOL_ERROR
```

Workaround — pre-stage a verified tarball so the build cannot touch the network:

```bash
curl --http1.1 -L -o linux-6.14.tar.xz \
  https://cdn.kernel.org/pub/linux/kernel/v6.x/linux-6.14.tar.xz
sha256sum linux-6.14.tar.xz
# must equal a294b683e7b161bb0517bb32ec7ed1d2ea7603dfbabad135170ed12d00c47670
sudo mkdir -p /var/cache/macbook12-audio-driver
sudo cp linux-6.14.tar.xz /var/cache/macbook12-audio-driver/
```

> `sudo ./install.cirrus.driver.sh -u` **deletes `/var/cache/macbook12-audio-driver/`
> entirely**, tarball included. Re-stage it after every uninstall.

The input failure is an intermittent boot race, not a 6.14-only bug
([input.md](input.md)). That unblocked this test; it was run; speakers stayed
silent. 6.14 was removed after the 7.0 stack worked.

---

## The verdict

> **Does the MacBook8,1's amplifier respond to the A1534 init sequence?**
> **No.** Tested 2026-09-01 on kernel 6.14.0-37.

The driver was built and installed on 6.14 and it **works as designed** — this is not
a failed install:

| Check | Result |
|---|---|
| Module loaded | `updates/dkms/snd-hda-codec-cirrus.ko.zst` |
| Kernel crashes | **0** (the 7.0 oops is specific to the >= 6.17 `cs420x.c` path) |
| Amp GPIO | `IO[0]: enable=1, dir=1, data=1` — but **mainline sets this too**, so it is not a differentiator |
| Speaker converter `0x0a` during playback | **`Power: D0`, `stream=1`** — powered and carrying audio |
| Speaker pin `0x1d` | `Pin-ctls: 0x40 OUT` |
| PipeWire | `Active Port: analog-output-speaker`, sink at 150%, unmuted |
| ALSA `Master` / `PCM` / `Line Out` | 100%, all `[on]` |
| `Auto-Mute Mode` | `Disabled` |
| Headphone jack sense | not plugged, so speakers are the correct target |
| **Audible output** | **none** |

Every stage of the chain is correct and live, and no sound comes out. The 2015 model's
amplifier therefore needs something the 2016/2017 sequence does not provide — a
different enable line, or an init step beyond asserting GPIO 0.

### The macOS warm-handoff attempt was inconclusive

Codec registers are not power-cycled by a restart, so the idea was: boot macOS (where
the speakers work), restart into Linux, and read what macOS left. Done 2026-09-01.

It proved nothing, because **the stock Linux driver sets GPIO 0 itself** (above), so a
GPIO 0 reading cannot be attributed to macOS. The state after the handoff was identical
to a normal Linux boot apart from which converter the Analog PCM was bound to
(`0x02` stock vs `0x04` under the out-of-tree driver, which hardcodes
`info->stream[PLAYBACK].nid = 0x04`).

The method is still sound — it just has to be **isolated** from Linux's own
initialisation. `snd_hda_intel` has a `probe_only=1` parameter that probes the codec and
exposes the proc dump **without running any init**. Comparing a cold `probe_only` boot
against a `probe_only` boot warm out of macOS yields exactly what macOS wrote, and
nothing else. That experiment has not been run yet.

### GPIO sweep and DigEn — ruled out, 2026-09-01

Done on stock 6.14 with headphones unplugged, a live 440 Hz stream on converter
`0x0a` (`conv=0x50`, power D0), and Digital Enable held at `0x111` for the whole
run. Scripts: [`bin/hda-dump`](../bin/hda-dump), [`bin/hda-gpio-sweep`](../bin/hda-gpio-sweep).
Baseline coefs: `~/codec-snapshots/stock-6.14-coefs.txt`.

| Try | Result |
|---|---|
| DigEn + SPDIF_STAT `0x20c4` during playback | silence |
| A1534 play GPIO (`mask=0x37 dir=0x31 data=0x01`) | silence |
| GPIO 4, 5, 2, 3, all-high, 0x1e/0x0b, A1534 reset dance | silence |

**Why none of that could have worked:** vendor coef **`0x1f = 0x400`**. That bit is
a latched CS4208 PLL clock fault. EFI leaves it at `0x0` (the boot chime plays);
stock `snd-hda-intel` pulses a controller reset on probe and **sets the latch**.
It cannot be cleared by any verb while a driver owns the link — which is why
poking GPIOs and DigEn on a running Linux session is a dead end.

The 2016/2017 `leifliddy/macbook12-audio-driver` never had to solve this; those
amps come up after a reset. The 2015 amp does not.

## What actually works

[thomas-shirley/macbook8.1-speaker-driver](https://github.com/thomas-shirley/macbook8.1-speaker-driver)
is a four-part DKMS stack for this exact machine (`0x10134208` / `0x106b6400`):

1. `snd-hda-intel` — attach to the live EFI link **without** a controller reset
2. `single_cmd=1 power_save=0` via `/etc/modprobe.d/mb81-singlecmd.conf`
3. `snd-hda-codec-cs420x` — write the EFI coef image; TDM prepare without the
   sync-dance that re-latches the clock
4. `snd-hda-codec-generic` — skip input-path / `init_digital` (those re-latch `0x1f`)

Cloned at `~/macbook8.1-speaker-driver`. DKMS name is still `macbook12-audio/0.1`.
Installed for **7.0.0-30-generic** only. `6.14` is kept as a boot fallback
(image + modules, no headers) so DKMS does not build for it.

### Build against Ubuntu HDA, not kernel.org

The installer's default of fetching kernel.org `sound/hda` panics at probe on
Mint's `linux-hwe-7.0` (same struct-ABI trap as leifliddy above). The working
tree is Ubuntu's `linux-hwe-7.0` orig tarball plus debian diff, with
`sound/hda` extracted under `~/macbook8.1-speaker-driver/build/ubuntu-src/`.
`install.cirrus.driver.sh` was patched locally to skip kernel.org for
`*-generic` kernels.

DKMS `CLEAN="rm -rf build"` also deleted the just-built `.ko` files; local
`dkms.conf` uses `CLEAN="true"`.

### Play through the EQ sink, not IEC958

ALSA devices after the patched driver:

| PCM | Role |
|---|---|
| `hw:PCH,0` | analog / headphones |
| `hw:PCH,1` | CS4208 Digital / IEC958 — **do not use** (shares converter `0x0a`) |
| `hw:PCH,2` | 4-channel TDM speakers |

PipeWire EQ (`~/.config/pipewire/pipewire.conf.d/51-macbook81-speaker.conf`, from
the driver) is the sink apps should use: **MacBook Speaker (EQ)** /
`input.MacBook_Speaker`. Its DSP output targets `MacBook_Speaker_Raw` (`hw:PCH,2`,
S16LE / 44100 / 4ch `FL FR RL RR`).

Mint 22 ships **WirePlumber 0.4.17**. The driver's
`~/.config/wireplumber/wireplumber.conf.d/51-mb81-rawpcm-speaker.conf` is
WirePlumber **0.5** SPA-JSON and is **ignored**, so ACP never exports device 2.
Chrome then followed the default EQ sink, whose DSP fell back onto IEC958 —
silent YouTube, no reboot required to fix. The WP 0.4 stand-in is a static
PipeWire adapter:

- repo: [`config/pipewire/52-macbook81-raw-sink.conf`](../config/pipewire/52-macbook81-raw-sink.conf)
- live: `~/.config/pipewire/pipewire.conf.d/52-macbook81-raw-sink.conf`

After copying, `systemctl --user restart pipewire pipewire-pulse wireplumber`.
A cold boot can still race the static adapter (card not ready yet); if speakers
are silent after login:

```bash
systemctl --user restart pipewire pipewire-pulse wireplumber
pactl set-default-sink input.MacBook_Speaker
```

Refresh any Chrome tab that was already playing. Confirm routing with
`pactl list short sinks` — `MacBook_Speaker_Raw` should exist, IEC958 should
be idle/suspended, default sink `input.MacBook_Speaker`.

### Checks after a 7.0 boot

```bash
dmesg | grep -i "attaching to running EFI link without reset"
modinfo -n snd-hda-intel snd-hda-codec-cs420x snd-hda-codec-generic
# expect .../updates/dkms/...
wpctl status | grep -i speaker
pactl get-default-sink   # input.MacBook_Speaker
```

`coef 0x1f` absent from a nonzero dump means `0` (locked). Bad is `0x400`.

### Headphone jack auto-switch

The CS4208 headphone DAC (`0x02`) and the TDM speaker converter (`0x0a`) share
an HDA stream tag. The speaker Raw node is pinned open, so a normal unplug
leaves the speakers silent. Mintbook's watcher is a local implementation for
the PipeWire/WirePlumber versions used here and does not embed the upstream
watcher script.

This machine's watcher is [`bin/mb81-jack-switch`](../bin/mb81-jack-switch),
enabled via `~/.config/systemd/user/mb81-jack-switch.service.d/override.conf`:

- **plug** — destroy `MacBook_Speaker_Raw`, switch the card to analog-stereo,
  default sink `alsa_output.pci-0000_00_1b.0.analog-stereo`
- **unplug** — `systemctl --user restart pipewire pipewire-pulse wireplumber`,
  default sink `input.MacBook_Speaker`

ACP still exposes IEC958 when the jack is unplugged — leave it unused.

Bluetooth audio needs `hci0`. That adapter is working on 7.0 after the
SSDC/UART DSDT override — [bluetooth.md](bluetooth.md). Not this codec.

### `mb81-resume-recover` fails on every resume — the greeter's PipeWire, 2026-09-09

`bin/doctor` reports `FAIL failed units mb81-resume-recover.service` under
Housekeeping. The unit is not mintbook's: `/usr/local/bin/mb81-resume-recover`
comes from the third-party MacBook8,1 speaker project's `install.sh`, alongside
`efi_recover.py`. Nothing in this repo references it.

It has never once succeeded on this machine — 2/2 runs failed, both identically:

```
=== 2/5: unload the whole HDA stack so 00:1b.0 sits UNOWNED ===
FAIL: 00:1b.0 still bound after unload:
/sys/bus/pci/devices/0000:00:1b.0/driver -> ../../../bus/pci/drivers/snd_hda_intel
Something still holds the module. Reboot to recover.
```

**The holder is the LightDM greeter's own PipeWire, running as uid 113.**

Step 1 of the script stops PipeWire, WirePlumber and the jack-switch *for one
user* — it resolves that user with
`loginctl list-users --no-legend | awk '$1>=1000{print $2; exit}'`, which yields
`cobo` and nothing else. But `pipewire.socket`, `pipewire.service` and
`wireplumber.service` are enabled `--global`, so **every** session gets a full
stack, including the greeter session LightDM opens on resume to draw the unlock
screen. That greeter is uid 113 — excluded by the `$1>=1000` filter, and by the
`exit` that stops at the first user regardless.

The interleaving is visible in the journal, and is the same on both runs:

```
21:30:44  lightdm[]: pam_unix(lightdm-greeter:session): session opened for user lightdm(uid=113)
21:30:44  sudo: COMMAND=/usr/bin/systemctl --user stop pipewire.socket ... wireplumber.service
21:30:44  kernel: snd_hda_codec_cs420x hdaudioC1D0: MB81 TDM CLEANUP   <- cobo's stream closes
21:30:44  systemd[1]: Started user@113.service - User Manager for UID 113
21:30:44  systemd[643958]: Started pipewire.service                    <- the greeter's
21:30:44  systemd[643958]: Started wireplumber.service                 <-   "
21:30:45  kernel: snd_hda_codec_cs420x hdaudioC1D0: MB81 TDM OPEN      <- greeter grabs the codec
21:30:46  mb81-resume-recover: FAIL: 00:1b.0 still bound after unload
```

`MB81 TDM OPEN` lands inside the script's single `sleep 1`, so `modprobe -r
snd_hda_intel` runs against a codec that was reopened about a second earlier.
The greeter's WirePlumber also logs `Error opening low-level control device
'hw:1'` in the same instant — it is enumerating cards while the script tears
them down.

The script's `2>/dev/null` on every `rmmod`/`modprobe -r` is why none of this
reached the log: the kernel's `Module snd_hda_intel is in use` never appeared,
so the failure said only "something still holds the module".

#### Measured, not assumed

Stopping the same units by hand, with no greeter session running, releases the
module fully and within the script's own 1-second budget:

```bash
systemctl --user stop mb81-jack-switch.service
systemctl --user stop pipewire.socket pipewire-pulse.socket \
    pipewire.service pipewire-pulse.service wireplumber.service
sleep 1; cat /sys/module/snd_hda_intel/refcnt      # 0
lsof /dev/snd/*                                    # empty
# undo:
systemctl --user start pipewire.socket pipewire-pulse.socket \
    pipewire.service pipewire-pulse.service wireplumber.service
sleep 3; systemctl --user start mb81-jack-switch.service
```

So the settle time is adequate and no ordinary desktop app holds `/dev/snd`
directly — refcount tracks open card fds exactly (4 fds open = `refcnt` 4:
`controlC0` from pipewire, wireplumber and alsactl, plus `pcmC0D1p` from
pipewire). Firefox and the Electron apps play through PipeWire and never appear.
`user@113.service` happens to be inactive between greeter appearances, which is
why the failure looks intermittent from `lsof` but is in fact 2/2.

#### Side effect: HDMI audio stays dead until reboot

Step 2 unbinds `0000:00:03.0` (the Broadwell-U HDMI controller, `card1` at boot)
*before* the unload it never completes, then exits without rebinding it. After a
failed run `/proc/asound/cards` lists only the PCH card, and
`/sys/bus/pci/devices/0000:00:03.0/driver` is gone until the next boot.

Every Audio check in `bin/doctor` still passes, because they all look at the
CS4208 on card 0. Internal speakers genuinely work — the codec never needed
healing on these s2idle cycles (`coef 0x1f` was not latched), which is the other
half of why a permanently red unit is misleading here.

#### Not yet fixed

`/usr/local/bin/mb81-resume-recover` is root-owned, outside this repo, and
replaced by the upstream `install.sh`. Nothing has been changed yet — see the
open question in the commit that added this section.

Do **not** clear it with `systemctl reset-failed mb81-resume-recover.service`.
That turns doctor green without the service working, and the next resume fails
again.

---

## Reverting

```bash
cd ~/macbook8.1-speaker-driver && sudo bash install.sh -r
rm -f ~/.config/pipewire/pipewire.conf.d/52-macbook81-raw-sink.conf
sudo reboot
```

The older 2016/2017 tree, if it is still around:

```bash
cd ~/macbook12-audio-driver && sudo ./install.cirrus.driver.sh -u
```

Verify recovery with: analog card back, and zero crash lines.

```bash
cat /proc/asound/cards                       # expect a PCH card, not just HDMI
dmesg | grep -cE "BUG:|Oops|UBSAN"           # expect 0
modinfo snd_hda_codec_cs420x | grep filename # expect kernel/... not updates/dkms/...
```

The in-tree module is ~16 KB; the DKMS build is ~90 KB. `lsmod` size is a quick tell
for which one is loaded.
