# Audio — internal speakers

**Status: UNSOLVED.** Headphone jack works. Internal speakers are silent and no
software configuration change has fixed it. This document records the full
investigation so it is not repeated from scratch.

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

- All six codec GPIOs read `enable=0` (`GPIO: io=6, o=2, i=0`). The amp enable line is
  never asserted.
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
`line_outs=5 (0x11/0x12/0x13/0x14/0x1d)` and a Digital PCM device appeared. But the
GPIOs still read `enable=0` and the speakers stayed silent.

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

### On kernel 6.14 it was never tested

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

**This is no longer blocked.** 6.14 was previously believed to have no working keyboard
or trackpad. That was wrong — it was a sample of two unlucky boots. The input failure is
an intermittent boot race that hits **both** kernels and has a fix; apply
[input.md](input.md) first, then 6.14 is a perfectly usable place to run this test.

---

## The actual open question

Everything above is about *getting the driver to run*. The question it exists to
answer is still unanswered:

> **Does the MacBook8,1's amplifier respond to the A1534 init sequence at all?**

If yes, this is solvable and worth real effort. If no, the 2015 model needs a
different init than the 2016/2017 models — the genuinely hard case, meaning the
sequence has to be reverse-engineered.

**That is not hopeless here: macOS is still installed** on this machine
(`nvme0n1p2`, 159 GB APFS — see [boot.md](boot.md)). macOS drives these speakers
correctly, so the working init sequence can in principle be captured from it. That is
exactly how the 9,1/10,1 sequence in `patch_cirrus_a1534_setup.h` was produced. It is
a large job, but the reference implementation is sitting on the same disk.

Do not invest in fixing the 7.0 ABI problem until this question is answered, because
a cleanly-initialising driver that still produces no sound is worth nothing.

## Next options, in order of cost

1. **Get input working on 6.14**, then install the driver there. Cheapest real test —
   it uses the mature code path and everything else is already staged.
2. **Rebuild against Ubuntu's own kernel source for 7.0.** Enable `deb-src` and
   `apt-get source linux-hwe-7.0`, then point the build at that tree instead of the
   kernel.org tarball. Note `linux-source-6.8.0` is the only packaged kernel source in
   the archive — there is no packaged 7.0 shortcut.
3. **Accept the workaround.** The headphone jack works; a USB-C audio adapter or DAC
   bypasses this codec entirely.

**Bluetooth audio is not an option.** There is no Bluetooth adapter present at all —
`/sys/class/bluetooth/` is empty and `rfkill` lists only the WLAN device. That is a
separate BCM4350 firmware problem.

---

## Reverting

```bash
cd ~/macbook12-audio-driver && sudo ./install.cirrus.driver.sh -u
sudo reboot
```

Verify recovery with: analog card back, and zero crash lines.

```bash
cat /proc/asound/cards                       # expect a PCH card, not just HDMI
dmesg | grep -cE "BUG:|Oops|UBSAN"           # expect 0
modinfo snd_hda_codec_cs420x | grep filename # expect kernel/... not updates/dkms/...
```

The in-tree module is ~16 KB; the DKMS build is ~90 KB. `lsmod` size is a quick tell
for which one is loaded.
