# Desktop application performance — 2026-09-06

**Done: Reduce motion is On.** Two interleaved comparisons showed substantially
lower CPU use while the active task was visible. The retained change is the app's
built-in preference; no graphics flags, drivers, or system animation settings changed.

This completed the first target in the next performance pass: desktop-app
overhead. Keep future comparisons within one workload and interleave settings.

## Handoff for the next session

- Leave Reduce motion **On**. The preference is set from the app's own settings
  UI, and it persists to `~/.codex/config.toml` as
  `reduced-motion-preference = "on"` under `[desktop]` — so it can be checked from
  a script, but this repository does not apply it on a new install.
- The user wants improvements tackled **one at a time, highest value first**.
- **Video is done — see [video.md](video.md).** It carries a do-not-re-test table.
  The short version: no Chromium can reach this GPU's H.264 decoder, Firefox can,
  and hardware H.264 encode is broken at the driver level. Do not re-open any of it.
- Subsequent candidates are a fresh real-workload Sustained-profile comparison,
  remaining panel overhead, and sleep recovery. Those were not changed here.
- Preserve the distinction between reduced CPU overhead, task completion speed,
  and battery life. Only the first was measured in this experiment.

## What was observed

- A 20-second sample during an active conversation measured about **37% of one
  logical CPU** across `ChatGPT` processes and **5.4%** in Xorg. This is activity,
  not proof of unnecessary work. Four logical CPUs mean a 400% total ceiling.
- OpenGL reports accelerated Intel HD 5300 rendering. The app's GPU process has
  `i965_drv_video.so` mapped. That confirms library loading, not that every
  rendering or video operation uses hardware acceleration.
- The process with `libvk_swiftshader.so` mapped is the
  `on_device_model.mojom.OnDeviceModelService` utility. It used zero CPU in the
  sample. Its presence does **not** establish that the main UI renders in software.
- A later 26-second sample measured **2.46%** app CPU, **5.82 W** battery draw and
  **48.6 C** average package temperature. **Discard this as a visible-desktop
  baseline:** the user's session was inactive and LightDM's greeter session was
  active. A screenshot of the user's X display was black. This was not an
  optimization result.

## First controlled experiment: Reduce motion

The installed `/usr/lib/chatgpt/resources/app.asar` identifies the app as
`openai-codex-electron` version `26.901.51231`. Read-only inspection found a
built-in **Reduce motion** preference, with values `system`, `on`, and `off`
and a default of `system`. The UI confirmed **System** was selected before testing.
The UI includes rules that disable animations when reduced motion is enabled.
The measurements below establish its benefit for the sampled workload.

The official settings and troubleshooting pages were checked, but did not
document this preference in the material retrieved:

- <https://learn.chatgpt.com/docs/reference/settings>
- <https://learn.chatgpt.com/docs/reference/troubleshooting>

Procedure, after unlocking the desktop:

1. Inspect and record the current Reduce motion selection in app settings.
2. Return to the same visible task, let rendering settle, and sample it.
3. Turn Reduce motion on, return to that same task, and sample again.
4. Repeat the original/on comparison. Keep power profile, window size, visible
   content and workload equivalent. No unrelated tools or scrolling during samples.
5. Keep the change only with a useful measured result; otherwise restore the
   original preference. Record CPU variation, not just a single mean difference.

### Measured result

Four samples in order: System / On / System / On. Each ran for about 26 seconds
after a four-second settling delay, on the same maximized task. The agent waited
on the sampler without streaming prose or running unrelated commands during each
window. The session remained active and unlocked. The machine was charging;
Balanced / `max_perf_pct=100` was verified at the end.

All numbers below are **CPU time as a percentage of one logical CPU**. The GPU
process column is CPU used by that process, not GPU utilization.

| Sample | App total | GPU process (part of app) | Xorg | xfwm4 |
|---|---:|---:|---:|---:|
| System 1 | 114.78% | 72.27% | 28.35% | 7.42% |
| On 1 | 45.88% | 15.10% | 5.52% | 1.46% |
| System 2 | 95.44% | 66.65% | 27.04% | 6.86% |
| On 2 | 33.91% | 15.79% | 5.29% | 1.38% |
| **System mean** | **105.11%** | **69.46%** | **27.70%** | **7.14%** |
| **On mean** | **39.90%** | **15.45%** | **5.41%** | **1.42%** |

App CPU fell **62%** in this comparison; GPU-process CPU fell **78%**, and
Xorg CPU fell **80%**. The app saving of 65.2 percentage points exceeds the
19.3-point spread between System samples and the 12.0-point spread between On
samples. The clearest evidence is the reversal: returning to System brought
GPU-process and Xorg CPU back up, and turning On reduced them again.

This is two repetitions, not a statistical confidence interval. Conversation
length and the visible tool row evolved between samples, so the screen was not
pixel-identical. PipeWire also varied (System 3.62/3.96%, On 3.07/2.99%), which
limits attribution of small effects; it does not explain the much larger
rendering difference. Do not generalize these numbers to every app screen.

No battery saving is claimed: battery watts are null while charging, and thermal
drift makes screenshots of temperatures unsuitable as an A/B result. Raw samples:
[2026-09-06-reduce-motion.json](measurements/2026-09-06-reduce-motion.json).

### Retained setting and undo

**Settings → Appearance → Preferences → Reduce motion → On.** It applies
immediately, without restarting. Selection was checked visually, including after
leaving and re-entering settings during the comparison.

Undo: select **System**, the original value, in the same control. Do not replace
this with global GTK animation changes or disable hardware acceleration.

Quiet rendering and streaming are different workloads. A quiet test can establish
the cost of ongoing animations while an agent is working, but cannot establish a
typing, scrolling, streaming, or whole-app speedup. Battery readings over short
windows are supporting observations, not precise savings estimates.

## Sampler

```bash
bin/app-probe --seconds 25 --label motion-system-visible
bin/app-probe --seconds 25 --label motion-on-visible
```

Read-only; no sudo. JSON includes process roles, interval CPU, exited-child CPU
separately, and battery watts while discharging. It omits command lines and app
content. Electron rewrites its process title into a space-separated string on
this installation; parsing only NUL-separated argv had hidden all process roles.

The sampler rejects an inactive/locked session and checks session state every
five seconds plus both endpoints. It also rejects mixed discharging/non-discharging
windows. It cannot detect every brief state change, user interaction, or change
of foreground window: keep those controlled manually. Processes absent at either
endpoint are omitted, so this is intended for stable desktop processes rather
than measuring a short-lived command tree.

Validation: CLI help and duration validation; live inactive-session rejection;
four valid active-desktop samples with process-role output and charging watts
correctly omitted. GPU acceleration was preserved and the live power policy
still matched the AC default after testing.
