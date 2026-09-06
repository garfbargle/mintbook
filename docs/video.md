# Video playback — 2026-09-06

**Chrome never hardware-decodes video on this machine, whatever `chrome://gpu` says.**
Forcing H.264 instead of AV1 is a real but modest win: about **11% less Chrome CPU**
and roughly a **quarter fewer dropped frames**. It does not make 720p60 playable.

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
