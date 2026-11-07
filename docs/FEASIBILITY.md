# Technical feasibility report (Phase 1)

Everything below was checked on the target machine — Windows 11, Python 3.14.9,
Hermes Agent v0.23.0+381.g6b21d05, AmpliTube 5 installed at
`C:\Program Files\IK Multimedia\AmpliTube 5` — rather than assumed. Where a fact
could not be verified locally it is labelled **unverified** and the plugin is
built so that the unverified part is never a hard dependency.

---

## 1. Hermes Agent plugin API

**Verified by reading the installed source** (`hermes-agent/website/docs/developer-guide/plugins/index.md`,
`plugins/AGENTS.md`, `hermes_cli/plugins_context.py`) and by running the
validator against the finished plugin.

| Question | Answer |
|---|---|
| Plugin form | directory with `plugin.yaml` + `__init__.py` exposing `register(ctx)` |
| Where user plugins live | `$HERMES_HOME/plugins/<name>/` (`C:\Users\<user>\AppData\Local\hermes\plugins` here) |
| Registering a tool | `ctx.register_tool(name=..., toolset=..., schema=..., handler=..., description=..., emoji=...)` |
| Handler contract | `def handler(args: dict, **kwargs) -> str`; return a JSON **string**, never raise, accept `**kwargs` |
| Optional dependency gating | `check_fn=` on `register_tool` |
| Durable state | `plugins.plugin_storage.plugin_data_dir("<name>")` (survives update/remove; follows the profile) |
| Manifest fields used | `name`, `version`, `manifest_version: 2`, `description`, `author`, `license`, `homepage`, `tags`, `provides_tools`, `config_schema` |
| Settings access | `ctx.get_config(key, default=...)` → `plugins.entries.tone-forge.settings.<key>` |
| Validation | `hermes plugins validate <dir>` (15 checks) and `hermes plugins doctor <dir> --ci` (real discovery + `register()`) |

Two consequences designed into the code:

1. **`provides_tools` must match reality.** `hermes plugins validate` fails when
   the declared list and the registered tools diverge, so the manifest lists all
   16 and `register()` registers exactly those 16.
2. **Do not import core internals.** Modules import only siblings
   (`from . import midi_io`) plus `plugins.plugin_storage` — and that last one is
   wrapped in `try/except` so the test suite can load the package outside Hermes.

One environment detail that shapes testing: this profile runs plugins in the
**plugin host** (`plugins.isolation: host`), i.e. in a per-profile subprocess.
`plugin_data_dir()` resolves the active profile's home in that child, so nothing
in the plugin caches a home path at import time.

---

## 2. MIDI on Windows — the decisive finding

### `python-rtmidi` does not install on this Python

```text
$ python3 -m pip download python-rtmidi --no-deps -d /tmp/rtd
Preparing metadata (pyproject.toml): finished with status 'error'
  error: subprocess-exited-with-error
      + meson setup ... -Dbuildtype=release ...
      UnicodeDecodeError: 'utf-8' codec can't decode byte 0x87 in position 5
      ..\meson.build:1:0: ERROR: Unhandled python exception
error: metadata-generation-failed
× Encountered error while generating package metadata.
╰─> python-rtmidi
```

There is no `cp314` wheel, so pip falls back to the sdist and the Meson build
fails before a compiler is even reached. `import rtmidi` → `ModuleNotFoundError`.

**This is not a corner case.** It is the normal state of affairs for a new CPython
release: a plugin that needs `python-rtmidi` is a plugin that silently does
nothing on the newest Python — exactly the machine a hackathon judge is likely
to use.

### The stdlib alternative works

Windows exposes MIDI output through `winmm.dll` (`midiOutOpen`,
`midiOutShortMsg`, `midiOutGetDevCapsW`), which `ctypes` can call directly.

```text
$ python3 winmm_probe.py
midiOutGetNumDevs: 1
0 0 'Microsoft GS Wavetable Synth' tech= 0x7 voices= 32
```

A live send was then performed through the finished plugin (not a scratch
script):

```text
$ python3 scripts/live_midi_check.py
active_backend: "winmm"   rtmidi available: false
port 0 = "Microsoft GS Wavetable Synth" (software synthesizer, 32 voices)
toneforge_set_parameter({"parameter": "gain", "value": 80})
  -> bytes_hex "B0 14 66"  (CC 20 = 102, channel 1)   rc 0
LIVE MIDI SEND: OK
after clearing the selection, send_midi returns ok = False
  error: ... ToneForge never sends to a port you did not choose.
```

### Decision

| Option | Verdict |
|---|---|
| Require `python-rtmidi` | ✗ unbuildable on Python 3.14 here; would make the plugin a no-op |
| Shell out to a MIDI CLI | ✗ arbitrary process execution, no dependency the user has |
| `mido` + backend | ✗ `mido` still needs rtmidi/portmidi underneath |
| **`ctypes` + `winmm` (primary) with `python-rtmidi` used when importable** | ✓ zero-dependency on Windows, portable elsewhere, one interface |

The backend is selected at runtime (`auto` → rtmidi if importable, else winmm) and
both satisfy the same three-method contract (`list_ports`, `send`, `close`), so
tests mock one object and cover both.

---

## 3. AmpliTube 5 MIDI capabilities

Source: the **official manual shipped with the installed copy**
(`C:\Program Files\IK Multimedia\AmpliTube 5\AmpliTube 5 User Manual.pdf`),
chapter 5 "MIDI Control", plus chapter 2.2 "Audio MIDI Setup".

| Fact | Consequence for ToneForge |
|---|---|
| "AmpliTube 5 responds to MIDI Control Change and Program Changes messages only. MIDI note numbers, aftertouch, pitch bend and other types of messages are not recognized" | Only `0xB0` CC messages are sent; no note/PC tricks. Documented, not guessed. |
| Standalone needs a MIDI **input** device chosen in Settings → Audio/MIDI | The loopback port must be selected inside AmpliTube as well; ToneForge cannot do it |
| Assignment path: right-click parameter → **Assign MIDI → [parameter] → Learn** | The mapping table is user-owned; ToneForge stores what the user learned |
| Alternative: Settings → **Control → Control Change → Global/Preset → Add → Learn** | `toneforge_midi_probe` exists to complete a Learn without touching hardware |
| "Global" scope covers only preset next/previous, volume pedal, wah, wharmonator and the 12 stomp bypasses | Amp-knob CCs are **Preset** scope → mappings carry `scope`, and `set_parameter` warns that a preset-scope mapping only works while that preset is loaded |
| Min/Max range values are **percentages**; 0%/100% = full travel; 100%/0% reverses | Mapping has `min`/`max` (raw CC) plus `param_min`/`param_max` (parameter units) and `invert` |
| Curve 0-10, default 5 = linear | ToneForge assumes linear and says so; a non-linear curve is the user's business |
| Receive channel is set by clicking the MIDI Channel display, 1-16 | Channel is a first-class tool parameter, validated 1-16 |

**Edition limitations (unverified):** the manual documents MIDI control as a
feature of AmpliTube 5 without an edition caveat, and this machine has an
AmpliTube 5 install (reported as the Standard edition; the edition was not
independently probed). What *is* edition- and collection-dependent is the
**model list** — AmpliTube 5 Standard ships fewer amps/cabs/pedals than MAX, and
Custom Shop gear extends it. ToneForge therefore never names a model: it names a
family, a character and browser search terms, and says plainly that the user must
pick the closest available model.

**What cannot be done, and is not attempted:**

- Building a chain inside AmpliTube remotely (no scripting/remote API; the app is GUI-only).
- Reading or writing native `.at5p` presets (undocumented binary container; fabricating one risks a corrupt preset and a wasted trial).
- Reading the current value of a knob back from AmpliTube (MIDI-in only; no state query).
- Confirming that a CC changed anything (see above). `applied: "unverified"` is the honest report.

---

## 4. What the plugin therefore commits to

1. Tone recipes are **generated, explained and stored** — fully working, no external dependency.
2. MIDI **egress** is real and verified (3 bytes, correct status byte, correct channel).
3. MIDI **ingress** depends on the user's AmpliTube assignment; the plugin supplies the mapping table, the Learn helper and the exact click-path documentation, and never pretends to have verified the result.
4. Everything runs **offline**, with **no third-party Python packages**, and writes only under the plugin's data directory.

## 5. Residual risks

| Risk | Mitigation |
|---|---|
| AmpliTube resets preset-scope assignments when a preset is overwritten | documented; re-Learn after re-saving a preset in AmpliTube |
| User assigns CCs that collide with global controls (volume, wah) | suggested layout starts at CC 20 and avoids CC 0-19 and 64/120-127 |
| loopMIDI not running when Hermes starts | nothing is cached at import; port list is queried per call |
| Device disappears mid-session | a failed `midiOutShortMsg` drops the cached handle and raises `MidiSendError` instead of silently retrying elsewhere |
| Python version without rtmidi wheel | winmm backend is the default on Windows, so the plugin still works |
