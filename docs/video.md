# Video playback — 2026-09-06

**Chrome never hardware-decodes video on this machine, whatever `chrome://gpu` says.**
Forcing H.264 instead of AV1 is a real but modest win: about **11% less Chrome CPU**
and roughly a **quarter fewer dropped frames**. It does not make 720p60 playable.

**Thorium beats Chrome and is still software:** 2.7% of frames dropped against
Chrome's 19.5%, bought with more CPU, not with the GPU.

**The hardware decoder itself is fine — and costs one fourteenth of the CPU.**
GStreamer's `vah264dec` needs 0.023 CPU-seconds per second of 720p60 video where
software needs 0.313. Chrome just will not use it. **Firefox will**, and the same
clip that costs Chrome a fifth of its frames plays in Firefox with 0.2% dropped.
**Hardware H.264 encode, by contrast, is not gated but broken:** the i965 encoder
advertises the entrypoint and then aborts.

## In plain terms

This chip has a small dedicated circuit for playing H.264 video. Using it is nearly
free. Not using it means the main processor decodes every frame by hand, and on a
fanless four-thread machine that shows up as heat, throttling, and stutter.

**Chrome cannot use that circuit.** Neither can Thorium, or any Chromium. They decode
in software. **Firefox can, and does.** On the same test video:

| Browser | Frames it failed to show | CPU used |
|---|---|---|
| **Firefox** (hardware decoding on) | **1 in 400** | 64% of one core |
| Thorium | 1 in 37 | 99% of one core |
| Chrome | **1 in 5** | 93% of one core |

One in five dropped frames is what visible stutter looks like. One in 400 is
indistinguishable from perfect.

A second, smaller point: **YouTube sends this machine AV1 by default**, a newer format
this GPU has no circuit for and is expensive to decode in software. Asking for the
older H.264 helps in any browser, and is what makes the Firefox result possible at all
— the hardware circuit only understands H.264.

### What to do

1. **Watch video in Firefox.** This is the whole win. Nothing else comes close.
2. **In Firefox, turn off VP9 and AV1** so YouTube sends H.264, which is the format
   the hardware can decode. Prefs are listed below.
3. **Prefer Thorium over Chrome** for everything else. It is measurably the better
   Chromium on this machine — just not a video player.
4. `enhanced-h264ify` in Chrome or Thorium is a small free improvement, worth having,
   not worth much.
5. **Do not chase hardware video encoding.** It is broken at the driver level here.

Everything below is the evidence and the exact settings.

## The headline correction

[hardware.md](hardware.md) said, from a `chrome://gpu` export: *"Decode was already
working… it does [use VA-API], and it did so before the driver change."* That read the
**capability list**, which is Chrome describing what the GPU could do. The media
pipeline disagrees.

Asked directly, over the DevTools `Media` domain, while actually playing:

| Stream | `kVideoDecoderName` | `kIsPlatformVideoDecoder` |
|---|---|---|
| YouTube default (AV1, 720p60) | `Dav1dVideoDecoder` | **false** |
| YouTube forced H.264 (720p60) | `FFmpegVideoDecoder` | **false** |
| Plain `.mp4` over HTTP, H.264 480p, no MSE | `FFmpegVideoDecoder` | **false** |

**Every path is software.** `chrome://gpu` advertising *"Video Decode: Hardware
accelerated"* with an h264/vp8 profile list is Chrome reporting the driver's
capability, **not** what the decoder stack chose. Do not use that page as evidence
about a real video again — ask the `Media` domain.

### It is not the driver, and it is not a missing flag

Tried, each on a throwaway profile, each re-checked with the `Media` domain — **all
still `FFmpegVideoDecoder`**:

- `LIBVA_DRIVER_NAME=i965` (this machine's setting) — software.
- `LIBVA_DRIVER_NAME` unset, so libva auto-selects **iHD** — software. Both drivers
  were confirmed mapped into the GPU process.
- `--ignore-gpu-blocklist`, `--use-gl=angle --use-angle=gl`, and
  `--enable-features=` with every plausible spelling drawn from the binary's own
  symbols: `AcceleratedVideoDecodeLinuxGL`, `kAcceleratedVideoDecodeLinuxGL`,
  `kAcceleratedVideoDecodeLinuxZeroCopyGL`, `VaapiIgnoreDriverChecks`, `Vaapi`.

**This clears the i965 decision of blame.** A reasonable worry was that forcing the
legacy driver had cost Chrome hardware decode, since Chrome vets VA drivers
(`kVaapiIgnoreDriverChecks` is in the binary). It had not: iHD decodes in software
here too. i965 remains the right choice for the reasons in
[hardware.md](hardware.md).

## Measured: AV1 versus H.264, same video

Chrome 152, throwaway profile, `Big Buck Bunny 60fps 4K` on YouTube pinned to
**1280x720@60**, muted. Four samples interleaved default / forced / default / forced,
25 seconds each after a 12-second settle. Machine **charging**, `balanced`,
`max_perf_pct=100`.

H.264 was forced the way `enhanced-h264ify` does it — overriding
`MediaSource.isTypeSupported` to reject `vp9`/`av01` — injected before page scripts
via the DevTools protocol, so **no extension was installed** to get this number.

CPU is percent of **one** logical CPU; four threads means a 400% ceiling.

| Sample | Codec YouTube served | Chrome CPU | Dropped / total frames | Package temp |
|---|---|---:|---:|---:|
| default-1 | `av01.0.08M.08` | 179.62% | 506 / 1627 (31.1%) | 93.8 C |
| h264-1 | `avc1.4d4020` | 163.92% | 429 / 1629 (26.3%) | 93.7 C |
| default-2 | `av01.0.08M.08` | 184.14% | 645 / 1626 (39.7%) | 94.4 C |
| h264-2 | `avc1.4d4020` | 160.73% | 395 / 1608 (24.6%) | 93.6 C |
| **AV1 mean** | | **181.88%** | **35.4%** | 94.1 C |
| **H.264 mean** | | **162.32%** | **25.4%** | 93.7 C |

**YouTube's default here is AV1, not VP9.** The docs assumed VP9 was the thing to
avoid. AV1 is worse, and Broadwell has silicon for neither.

**CPU: a real 10.8% saving.** The 19.6-point gap between the means is well clear of
the spread within each condition (4.5 points for AV1, 3.2 for H.264).

**Dropped frames: better, but claim this one more softly.** 35.4% to 25.4% is a
useful direction, but the two AV1 samples were 8.6 points apart on their own, which
is nearly as large as the 10-point effect. Two repetitions cannot separate those
cleanly.

**Temperature says nothing.** The package sat at 91–95 C in every sample, start to
finish. The machine was thermally saturated before the first sample began, so this
experiment cannot measure a heat difference. No battery claim either — `battery_w`
is null while charging.

## What this actually means

**720p60 is not playable on this machine in Chrome, in any codec.** A quarter of
frames dropped is not "slightly worse", and the media pipeline reported repeated
`DECODER_UNDERFLOW`. Forcing H.264 moves it from very bad to bad.

So `enhanced-h264ify` is **worth installing but is not a fix**: it buys about 11% of
Chrome's CPU on video, for free, with no measured downside beyond losing higher-quality
VP9/AV1 renditions that this machine cannot decode anyway.

The larger question this opens: **something ought to be able to use the H.264 decoder
this GPU demonstrably has.** `vainfo` reports `VAProfileH264High : VAEntrypointVLD`
under i965. Chrome will not touch it. Not yet tested here — Firefox is installed and
has its own VA-API path (`media.ffmpeg.vaapi.enabled`), and `gst-launch-1.0` is
installed for a decoder-level test that takes the browser out of the picture entirely.

## The decoder works. Chrome is simply not using it.

Taking the browser out of the picture entirely, with GStreamer decoding a local
file to `fakesink` — no window, no compositing, decode only. The clip is 1500
frames of 720p60 H.264 High profile, 25.0 seconds, encoded locally with `x264enc`
so that nothing had to be downloaded.

| Run | Decoder | Wall | CPU of one core | CPU seconds |
|---|---|---:|---:|---:|
| sw-1 | `avdec_h264` | 4.63 s | 167% | 7.76 |
| hw-1 | `vah264dec` | 2.52 s | 21% | 0.53 |
| sw-2 | `avdec_h264` | 4.25 s | 180% | 7.68 |
| hw-2 | `vah264dec` | 2.56 s | 23% | 0.60 |
| sw-3 | `avdec_h264` | 4.46 s | 180% | 8.05 |
| hw-3 | `vah264dec` | 2.52 s | 23% | 0.57 |
| **software mean** | | **4.45 s** | **176%** | **7.83** |
| **hardware mean** | | **2.53 s** | **22%** | **0.57** |

**Hardware decode costs about one fourteenth of the CPU** — 0.023 CPU-seconds per
second of video against 0.313 — and finishes in a little over half the wall time.

The percentage column is **not** a playback figure: `sync=false` decodes as fast as
the machine allows, which was about 5.6x realtime for software. Divide the CPU
seconds by the clip's 25 s to get the realtime equivalent — **31.3% of one core for
software, 2.3% for hardware.**
The three repetitions are tight: the widest software spread is 0.38 s of wall time
against a 1.92 s effect.

The absolute software number is optimistic, not pessimistic: `videotestsrc
pattern=ball` is far easier to decode than real footage, so a real 720p60 stream
costs *more* than 176% of a core in software. The ratio is the finding.

**So this machine has a working, very cheap H.264 decoder, and Chrome leaves the
whole thing on the table.** That reframes `enhanced-h264ify` from "the fix" to "a
consolation prize": it saves 11% of Chrome's CPU by picking a codec Chrome then
decodes in software anyway.

## Hardware H.264 *encode* is not merely gated — it is broken

[hardware.md](hardware.md) reasoned that since `vainfo` reports
`VAProfileH264High : VAEntrypointEncSlice` under i965, the encoder existed and only
Chrome's gate stood in the way. **The entrypoint is advertised and the encoder
aborts.** Both GStreamer plugins, same result:

```
gst-launch-1.0: i965_encoder.c:1692: intel_enc_hw_context_init:
        Assertion `encoder_context->mfc_context' failed.
```

`vah264enc` and the older `vaapih264enc` both dump core on the first frame at
720p60. Under iHD the element does not register at all, matching the "no encode
entrypoint" finding already recorded.

**There is no working H.264 hardware encoder on this machine, in any driver.**
Chrome's refusal to use it costs nothing. Close this thread for good: an
advertised VA-API entrypoint is a claim, and this one is false.

## Thorium: really is better than Chrome, and still software

Thorium 152 is installed here (`152.0.7977.55 stable, built on Ubuntu (AVX2)`). The
impression that it handles video better than Chrome is **correct and measurable** —
and the reason is not hardware decoding.

Chrome and Thorium interleaved, two samples each, same clip and window as above:

| Sample | CPU | Frames dropped |
|---|---:|---:|
| chrome-1 | 97.87% | 315 / 1555 — 20.3% |
| thorium-1 | 98.85% | 46 / 1614 — 2.9% |
| chrome-2 | 88.57% | 303 / 1616 — 18.8% |
| thorium-2 | 99.96% | 40 / 1614 — 2.5% |
| **Chrome mean** | **93.22%** | **19.5%** |
| **Thorium mean** | **99.41%** | **2.7%** |

**Thorium drops about a seventh of what Chrome drops**, and the effect dwarfs the
spread (1.5 points within Chrome, 0.4 within Thorium). It buys that with about six
points more CPU: it is not cheaper, it is *faster*, which is exactly what an AVX2
build of the same Chromium should be. Chrome gave up and dropped frames; Thorium
spent the cycles and kept them.

**But it is still software.** `kVideoDecoderName` is `FFmpegVideoDecoder` with
`kIsPlatformVideoDecoder: false`, and it stays that way with `--ignore-gpu-blocklist`
and every VA-API feature spelling forced. Thorium carries the same Chromium decode
code and the same symbols. **The whole Chromium family is locked out of this GPU's
decoder here.** Only Firefox gets in.

So Thorium is the right Chromium to use on this machine, and it is still the wrong
tool for a long video: it holds 60 fps by burning a full core, where Firefox holds
it on 64% of one.

## Firefox does use the decoder. Same machine, same clip.

This is the finding worth acting on. Firefox 155 hardware-decodes H.264 here and
plays 720p60 essentially perfectly, where Chrome drops a fifth of the frames.

Same local clip, same 1280x720 element, each browser measured alone with
[`bin/app-probe`](../bin/app-probe) while its window was focused. Frame counts come
from `getVideoPlaybackQuality()` published into the window title and read back with
`xdotool`, so they are the browser's own accounting.

| Browser | Decode | CPU | Frames dropped |
|---|---|---:|---:|
| Chrome 152 | software (no choice) | 95.2% | **318 / 1612 — 19.7%** |
| Firefox 155, hardware decoding **off** | software | 66.7% | **504 / 1623 — 31.1%** |
| Firefox 155, hardware decoding **on** | **VA-API** | 63.8% | **4 / 1624 — 0.2%** |

**Read the frame column, not the CPU column.** The two Firefox rows are only three
points apart on CPU, which looks like the hardware decoder barely helps. It is an
artefact: the software run was *dropping a third of its frames*, so it was doing
less work for its 66.7%. The hardware run did all the work for less. CPU alone
would have led to the wrong conclusion here.

Isolating the decoder makes it unambiguous — Firefox decodes in a separate
`RDD Process`, so it can be read on its own:

| | RDD Process CPU | VA driver mapped in RDD |
|---|---:|---|
| hardware decoding on | **14.07%** | `i965_drv_video.so` |
| hardware decoding off | 25.25% | none |

The driver is mapped only in the hardware case, and only while H.264 plays. That is
the same `i965` this machine forces in [hardware.md](hardware.md) — **so the driver
work was worth something after all, just not to Chrome.**

### End to end on YouTube

Firefox with VP9 and AV1 turned off, on the same 720p60 video Chrome was tested
with:

| | Chrome, forced H.264 | Firefox, forced H.264 |
|---|---:|---:|
| Total browser CPU | 162.32% | **105.55%** |
| Decoder process | not separable | **13.11%** |
| Codec served | `avc1.4d4020` | `h264` |
| VA driver in decoder | none | **`i965_drv_video.so`** |

**Frame drops on YouTube were not measured for Firefox** — there is no injection
path into a Firefox page the way there is over Chrome's DevTools protocol, and the
title trick only works on a page we control. The local-clip result above is the
frame-drop evidence; this table is CPU and decoder identity only.

### The configuration that was tested

In a throwaway profile:

```
media.hardware-video-decoding.enabled       true      // the actual VA-API gate
media.hardware-video-decoding.force-enabled true
media.mediasource.vp9.enabled               false     // make YouTube serve H.264
media.av1.enabled                           false
media.webm.enabled                          false
gfx.webrender.all                           true
gfx.x11-egl.force-enabled                   true
```

plus `MOZ_X11_EGL=1` in the environment.

**Which of these are actually required was not isolated** — they were set together
and the result was measured as a set. `media.hardware-video-decoding.enabled` is
certainly load-bearing, since flipping that one alone turned VA-API off and the
frame drops on. `media.webm.enabled=false` is the most suspicious of the rest: it
is heavier than needed and will affect sites beyond YouTube. Narrowing this to the
minimum set is the obvious next job, and none of it is installed on the real
profile yet.

Two things that are **not** the gate, despite looking like it:
`media.ffmpeg.vaapi.enabled`, which every guide still recommends, **is not a pref in
Firefox 155 at all** — it is absent from `libxul.so`, so setting it does nothing.
And the log description stays `ffmpeg video decoder` whether or not VA-API is in
use; it is not a hardware indicator. Check the RDD process for a mapped
`*_drv_video.so` instead.

### What to do

**Watch video in Firefox on this machine, with VP9 and AV1 disabled.** That is the
whole recommendation. It is the difference between 0.2% and 20% of frames dropped
at 720p60. `enhanced-h264ify` in Chrome remains a small, free improvement for
whatever stays in Chrome, but it is not in the same category as this.

## Method

Raw samples: [2026-09-06-youtube-codec-ab.json](measurements/2026-09-06-youtube-codec-ab.json).

Ask the pipeline, not the capability page:

```
CDP: Media.enable  ->  Media.playerPropertiesChanged
     kVideoDecoderName, kIsPlatformVideoDecoder
```

`kIsPlatformVideoDecoder: false` means software, whatever `chrome://gpu` claims.
CPU came from [`bin/app-probe`](../bin/app-probe) run concurrently, summing rows whose
process name is `chrome`; it rejects locked or inactive sessions and mixed power states.

Two traps worth remembering. The `youtube-nocookie.com/embed/` URL returns **Error 153**
for this video, so use the ordinary watch page. And a sample is only comparable if the
rendition matches: pin it with `setPlaybackQualityRange('hd720','hd720')` and confirm
`videoWidth`/`videoHeight` in the result rather than trusting it.
