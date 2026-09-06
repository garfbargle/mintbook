# Video playback — 2026-09-06

**Chrome never hardware-decodes video on this machine, whatever `chrome://gpu` says.**
Forcing H.264 instead of AV1 is a real but modest win: about **11% less Chrome CPU**
and roughly a **quarter fewer dropped frames**. It does not make 720p60 playable.

**The hardware decoder itself is fine — and costs one fourteenth of the CPU.**
GStreamer's `vah264dec` decodes 720p60 at 22% of one core where software needs 176%.
Chrome just will not use it. **Hardware H.264 encode, by contrast, is not gated but
broken:** the i965 encoder advertises the entrypoint and then aborts.

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
