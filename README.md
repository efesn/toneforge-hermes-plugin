# ToneForge

[![CI](https://github.com/efesn/toneforge-hermes-plugin/actions/workflows/ci.yml/badge.svg)](https://github.com/efesn/toneforge-hermes-plugin/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

**An AI guitar tone engineer for [IK Multimedia AmpliTube 5](https://www.ikmultimedia.com/products/amplitube5/) inside [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Describe a tone in plain language — *"industrial metal for Drop D, tight low end, Rammstein-ish"* — and ToneForge returns a complete, musically-reasoned recipe: signal chain in order, amp and cab character, mic position, pedal settings, 7-band EQ, noise gate, and normalised gain/bass/mid/treble/presence/master values, with an explanation of *why* each choice was made. It can then drive the MIDI CCs you assigned in AmpliTube to move the knobs you mapped.

ToneForge is explicit about the boundary between **designing a tone** and **changing AmpliTube**:

| ToneForge does | ToneForge does not |
|---|---|
| Generate a full tone recipe you can dial in by hand | Insert models, change amp sims, or click inside AmpliTube for you |
| Store, list, version, adjust and delete its own JSON presets | Write native AmpliTube `.at5p` preset files |
| Send MIDI CC messages to a loopback port you selected | Guess that CC 20 "is" amp gain — AmpliTube has no such default |
| Report exactly which bytes went out and on which port | Claim a parameter changed (only AmpliTube can show that) |
| Explain every parameter move, with before/after values | Promise an exact reproduction of a recorded guitar tone |

---

## Status — what is actually verified

Last verified locally on **Windows 11, Python 3.14.9, Hermes Agent v0.23.0+381.g6b21d05**:

- `python -m unittest discover -s tests` → **139 tests, all passing** (no MIDI hardware, no AmpliTube, no network).
- `hermes plugins validate ./tone-forge` → **Validation passed** (all 15 checks).
- `hermes plugins doctor ./tone-forge --ci` → **16 tools registered**, runtime discovery + import + `register(ctx)` OK.
- `scripts/live_midi_check.py` → **a real Control Change message left the machine** through the built-in Windows `winmm` driver (`B0 14 66`, i.e. CC 20 = 102 on channel 1), and the no-port-selected safety path refused to send.

The same unit suite runs in GitHub Actions on Windows and Linux across supported Python versions. **No screenshot, demo recording, or test result in this repository is staged or fabricated.**

Not verified on this machine, and therefore not claimed anywhere in the plugin:

- **AmpliTube receiving the message.** AmpliTube 5 is installed here, but no virtual MIDI loopback port (loopMIDI) is, so there is no path from ToneForge's output into AmpliTube's input. The last hop is a five-minute manual step — see [Windows MIDI setup](#windows-midi-setup).
- **Exact AmpliTube model names.** Model availability differs between AmpliTube 5 editions and Custom Shop collections, so profiles describe amp/cab/mic **families and characters** plus browser search terms, never "this model exists in your edition".

---

## Features

**Tone design**

- Nine hand-built profiles: Industrial Metal, Modern Metal, Thrash Metal, Metalcore, Hard Rock, Classic Rock, Clean, Ambient, Lead/Solo.
- A deliberately detailed **industrial-metal / Drop D** starting point: tight low end, controlled high end, defined mids, hard gate, optional overdrive in front.
- Tuning compensation for 10 tunings (standard → Drop A, 7-string), pickup compensation for 6 pickup types, purpose shaping for 6 roles (rhythm/lead/solo/clean/ambient/crunch).
- Free-text shaping in English **and Turkish**: `tighter`, `more mids`, `less muddy`, `add presence`, `djent`, `doom`, `daha sıkı`, `gain azalt`, `mid artır`, `daha kuru`, plus explicit `set gain to 75`.
- Deterministic output: the same request always produces the same recipe, which makes presets reproducible and tests meaningful.

**Preset library**

- JSON presets with schema version, slug, version counter, timestamps and notes.
- Overwrite protection (explicit `overwrite=true` required), confirmation-gated deletes, atomic writes, path-traversal-proof slugs.
- Adjust a stored preset without touching it; save the result in place (version bump) or under a new name.

**MIDI bridge**

- Two backends: the **stdlib `winmm` driver via `ctypes`** (no dependency at all on Windows) and optional **`python-rtmidi`** when it is installed.
- Port enumeration with loopback detection hints; explicit port selection persisted between sessions.
- User-owned CC mapping table: `toneforge_map_parameter` records what *you* assigned in AmpliTube, with CC range, channel, parameter range, inversion and AmpliTube scope (preset/global).
- `toneforge_set_parameter` converts a 0-100 value into that mapping's CC range and reports `bytes_hex`, channel, CC and value — and labels the result `applied: unverified`, because it is.
- `toneforge_midi_probe` sends a short `0 → 127 → 64` sequence to bind a CC during AmpliTube's MIDI Learn.
- Nothing is ever sent to a port the user did not select.

---

## Architecture

```text
┌──────────────────────────── Hermes Agent (desktop / CLI / TUI) ────────────────────────────┐
│  model calls a tool, e.g. toneforge_create_preset({genre: "industrial metal", ...})         │
└───────────────────────────────────────────┬────────────────────────────────────────────────┘
                                            │ JSON in / JSON string out
┌───────────────────────────────────────────▼────────────────────────────────────────────────┐
│ tone-forge plugin                                                                           │
│                                                                                             │
│  __init__.py      register(ctx) → 16 tools, settings (midi_backend, default_channel)         │
│  schemas.py       tool descriptions + strict JSON schemas (what the model sees)              │
│  tools.py         handlers: validate → work → JSON; never raises                            │
│                                                                                             │
│   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐   ┌────────────────┐              │
│   │ tone_engine  │   │ tone_profiles │   │ preset_store │   │ validation     │              │
│   │ build/adjust │◄──│ 9 profiles,   │   │ JSON presets │◄──│ ranges, slugs, │              │
│   │ modifiers    │   │ tunings, eq   │   │ atomic write │   │ path safety    │              │
│   └──────┬───────┘   └───────────────┘   └──────────────┘   └────────────────┘              │
│          │                                                                                  │
│   ┌──────▼───────┐   ┌───────────────┐                                                      │
│   │ midi_map     │   │ midi_io       │                                                      │
│   │ user CC      │──►│ winmm(ctypes) │───┐                                                  │
│   │ mappings     │   │ or rtmidi     │   │                                                  │
│   └──────────────┘   └───────────────┘   │                                                  │
└──────────────────────────────────────────┼──────────────────────────────────────────────────┘
                                           │ MIDI CC (3 bytes)
                              ┌────────────▼─────────────┐
                              │ loopMIDI virtual port    │  e.g. "ToneForge"
                              └────────────┬─────────────┘
                                           │ AmpliTube's selected MIDI Input
                              ┌────────────▼─────────────┐
                              │ AmpliTube 5 Standalone   │  reacts only to CCs you assigned
                              └──────────────────────────┘
```

| Module | Responsibility |
|---|---|
| `__init__.py` | `register(ctx)`: read settings, register 16 tools |
| `schemas.py` | Tool schemas and descriptions — the model-facing surface |
| `tools.py` | Handlers: validate args → call domain → JSON envelope |
| `tone_engine.py` | Resolve genre, apply tuning/pickup/purpose, instruction modifiers, render chain, diff adjustments |
| `tone_profiles.py` | Data: 10 tunings, 6 pickups, 6 purposes, 9 profiles, chain order, disclaimer |
| `preset_store.py` | JSON preset library: slugs, atomic writes, versioning, listing |
| `midi_map.py` | User CC mapping table + value conversion |
| `midi_io.py` | Backends (`winmm`, `rtmidi`), port selection, send, probe |
| `validation.py` | Ranges, text hygiene, slugs, path safety, error types |

No network calls, no subprocesses, no writes outside the plugin's data directory. Full rationale: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Requirements

| | |
|---|---|
| OS | Windows 10/11 (the `winmm` backend is Windows-only; `python-rtmidi` makes it portable) |
| Hermes Agent | 0.23.0 or newer (plugin API: `plugin.yaml` + `register(ctx)`) |
| Python | 3.10+ (tested on 3.14.9) — **no third-party packages required** |
| AmpliTube | AmpliTube 5 (Standard or higher), **Standalone** mode |
| Loopback MIDI | [loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html) (free) — required for the MIDI bridge |
| Audio | Any audio interface AmpliTube already works with |

---

## Installation

ToneForge is a Hermes plugin directory. It must sit exactly one level deep: `plugins/tone-forge/plugin.yaml`.

### Option A — clone the repository (recommended)

```bash
git clone https://github.com/efesn/toneforge-hermes-plugin.git "$HERMES_HOME/plugins/tone-forge"
hermes plugins enable tone-forge
```

### Option B — copy a local checkout

```bash
cp -r "/path/to/toneforge-hermes-plugin" "$HERMES_HOME/plugins/tone-forge"
hermes plugins enable tone-forge
```

### Verify the install

```bash
hermes plugins validate "$HERMES_HOME/plugins/tone-forge"
hermes plugins doctor  "$HERMES_HOME/plugins/tone-forge" --ci
python -m unittest discover -s tests
```

Expected: `Validation passed`, `16 tool(s)` registered, and `Ran 139 tests ... OK`.

`$HERMES_HOME` is `C:\Users\<you>\AppData\Local\hermes` on a default Windows install, or `~/.hermes`. Hermes loads plugin tools on the next session — restart the desktop app (or start a new `hermes` session) and the 16 `toneforge_*` tools appear.

Full walkthrough, including update and uninstall: [`docs/INSTALLATION_WINDOWS.md`](docs/INSTALLATION_WINDOWS.md).

---

## Usage examples

Inside Hermes, just talk. ToneForge selects the right tool; you do not need to name it.

### Create a tone

> Create a heavy industrial metal tone for Drop D, inspired by Rammstein's Sonne. Tight low end and controlled highs.

> Give me a Metallica-style rhythm tone in standard tuning, humbuckers.

> Make a modern metalcore tone for Drop C with a tight gate.

> Drop A, 7-string, maximum weight but no mud.

> Bunu daha sıkı yap, gain'i azalt. *(Turkish)*

### Adjust and save

> Make my guitar sound heavier but keep the note definition.

> Reduce the gain and increase the mids.

> Set the amp gain to 80.

> Save it as "Sonne Rhythm".

Adjustments return a field-by-field `{before, after}` change list and never mutate the stored preset unless you explicitly save.

### Manage the library

> What tones do I have?

> Show me the Sonne preset.

> Delete the test preset.

Profiles, tunings and purposes are inspectable:

> What profiles does ToneForge have?

### Example response (trimmed, real output)

For *"industrial metal for Drop D, tight low end, controlled highs, keep note definition"*:

```json
{
  "genre_label": "Industrial Metal",
  "tuning_label": "Drop D (D A D G B e)",
  "params": {
    "gain": 74, "bass": 33, "mid": 65,
    "treble": 52, "presence": 49, "master": 55
  },
  "gate": { "threshold_db": -51.0, "decay_ms": 50, "hold_ms": 20 },
  "eq": { "low_cut_hz": 92, "high_cut_hz": 11000 },
  "signal_chain": [
    "Noise gate",
    "Overdrive / clean boost (optional)",
    "Amplifier",
    "Cabinet + microphone",
    "7-band EQ",
    "Delay / reverb"
  ]
}
```

More prompts, expected tool calls and refusal cases: [`docs/EXAMPLE_PROMPTS.md`](docs/EXAMPLE_PROMPTS.md).

---

## Windows MIDI setup

The MIDI bridge needs a virtual cable from ToneForge to AmpliTube:

```text
Hermes + ToneForge ──CC──► loopMIDI port "ToneForge" ──► AmpliTube 5 (MIDI Input)
```

AmpliTube responds only to **Control Change** and **Program Change** messages, and only to CCs **you assigned inside AmpliTube**. Note numbers, aftertouch and pitch bend are ignored.

### 1. Create the loopMIDI port

1. Install **loopMIDI** from <https://www.tobias-erichsen.de/software/loopmidi.html>.
2. Launch it. It lives in the notification area (system tray) and must stay running.
3. In the **New port-name** field, type `ToneForge`, then click **+**.
4. Verify from Hermes: *"List my MIDI ports."* — `toneforge_list_midi_ports` should show `ToneForge` with `looks_like_loopback: true`.

If the port does not appear, restart loopMIDI and re-run the tool. Windows occasionally needs a second to register a new port.

### 2. Point AmpliTube 5 Standalone at the port

1. Open **Settings → Audio/MIDI**.
2. Set **MIDI input** to `ToneForge`. (`Any` also works, but a specific port is less surprising.)
3. Open **Settings → Control → Control Change**.
4. Confirm the **MIDI Channel** matches ToneForge's channel. ToneForge defaults to **1**.
5. Leave **Min/Max** at `0%` / `100%` and **Curve** at `5` (linear). ToneForge assumes linear 1:1 CC-to-parameter travel unless you record a different `param_max`.

### 3. Assign and record a CC

1. In AmpliTube, right-click the knob (for example, the amp **Gain**).
2. Choose **Assign MIDI → [parameter] → Learn**.
3. Ask Hermes: *"Probe CC 20 so AmpliTube learns it."* — `toneforge_midi_probe` sends `0 → 127 → 64`.
4. Tell ToneForge what you assigned: *"Map amp gain to CC 20."*
5. Drive it: *"Set the amp gain to 80."* → `80/100 → CC 102`, `bytes_hex: "B0 14 66"`, `applied: "unverified"`.

**Scope matters:** amp-knob CCs are **Preset** assignments in AmpliTube. They apply only to the current preset. **Global** scope covers only preset next/previous, volume pedal, wah, wharmonator and the 12 stomp bypasses.

### Verification checklist

- [ ] `toneforge_midi_status` → `active_backend: "winmm"` (or `rtmidi`), `ports_available ≥ 1`
- [ ] `toneforge_list_midi_ports` → `ToneForge` present, `looks_like_loopback: true`
- [ ] `toneforge_select_midi_port` → `ToneForge` selected
- [ ] AmpliTube: Settings → Audio/MIDI → MIDI input = `ToneForge`
- [ ] AmpliTube: Settings → Control → MIDI Channel = ToneForge channel
- [ ] A knob has the CC assigned (right-click → Assign MIDI → Learn)
- [ ] `toneforge_map_parameter` with that exact CC
- [ ] `toneforge_set_parameter` → `sent: true`, and the knob in AmpliTube moves
- [ ] `toneforge_midi_status` → `ready: true`

Full instructions, scope rules, mapping ranges and a 12-row troubleshooting table: [`docs/MIDI_SETUP_WINDOWS.md`](docs/MIDI_SETUP_WINDOWS.md).

---

## Tools (16)

| Tool | What it does |
|---|---|
| `toneforge_create_preset` | Build a complete tone recipe from genre/reference/tuning/pickup/purpose/gain/instructions; optionally save it. |
| `toneforge_adjust_preset` | Modify a stored preset or inline recipe in natural language; returns a before/after change list. Saves only with `save=true`. |
| `toneforge_save_preset` | Store a recipe (or duplicate an existing preset) as a JSON preset; refuses silent overwrites. |
| `toneforge_list_presets` | List the library, newest first. |
| `toneforge_get_preset` | Load one preset in full. |
| `toneforge_delete_preset` | Delete a preset; requires `confirm=true`. |
| `toneforge_list_profiles` | Show the 9 profiles, 10 tunings, 6 purposes and their starting parameters. |
| `toneforge_midi_status` | Backend in use, port selection, mapping count, blockers, and the verified AmpliTube setup checklist. |
| `toneforge_list_midi_ports` | Enumerate MIDI outputs, flag loopbacks, pick nothing. |
| `toneforge_select_midi_port` | Persist which output port to send to. |
| `toneforge_send_midi` | Send one raw CC (0-127) on a channel (1-16). |
| `toneforge_set_parameter` | Set a *mapped* parameter by name (0-100) after converting to its CC range. |
| `toneforge_map_parameter` | Record a CC assignment made in AmpliTube (or seed ToneForge's suggested layout). |
| `toneforge_list_mappings` | Show mappings and which suggested parameters are still unmapped. |
| `toneforge_remove_mapping` | Forget a mapping (AmpliTube is untouched). |
| `toneforge_midi_probe` | Send `0 → 127 → 64` on a CC to bind it during MIDI Learn. |

### Parameter scales

ToneForge uses three different units on purpose — mixing them up is the most common way a good recipe sounds wrong:

1. **Gain, bass, mid, treble, presence, master: 0-100**, ToneForge's own normalised scale. `75` is "high but not maxed". Map 0-100 onto the knob's full travel by ear.
2. **EQ: dB targets** for a 7-band graphic EQ at 100 / 200 / 400 / 800 / 1.6k / 3.2k / 6.4k Hz, plus high-pass and low-pass frequencies in Hz. Use them on an EQ pedal, or as "boost/cut this region" instructions for an amp's tone stack.
3. **Noise gate: dB threshold, ms decay, ms hold.** Lower threshold = more permissive.

For MIDI, `param_min`/`param_max` describe the parameter's range (0-100), while `min`/`max` describe the raw CC bytes (0-127). AmpliTube's own **Min/Max are percentages of the parameter range** — leave them at 0% / 100% and `Curve` at 5 (linear) for a 1:1 conversion.

---

## Data, privacy and security

| What | Path |
|---|---|
| Presets | `<HERMES_HOME>/plugin-data/tone-forge/presets/<slug>.json` |
| MIDI mappings | `<HERMES_HOME>/plugin-data/tone-forge/midi_map.json` |
| Selected port + channel | `<HERMES_HOME>/plugin-data/tone-forge/midi_config.json` |

**Privacy: nothing leaves the machine.** ToneForge stores what you tell it and sends MIDI to a port you chose; it never uploads a preset, a mapping or a byte of guitar audio.

Security properties enforced by the code and covered by tests:

- No `subprocess`, `eval`, `exec`, dynamic import of user strings, or network client anywhere in the plugin.
- Preset and mapping names are slugged and re-validated; path traversal (`../escape`, `..`, absolute paths) is tested and refused.
- Writes are restricted to `<HERMES_HOME>/plugin-data/tone-forge/`; atomic temp-file + `os.replace` writes prevent half-written files.
- MIDI output requires an explicit port selection or an explicit port argument on the very call that sends.
- The plugin never writes to AmpliTube's own files and never touches `Documents/IK Multimedia/AmpliTube 5/`.
- No credentials or tokens are read, stored or transmitted.

See [`SECURITY.md`](SECURITY.md) for the reporting policy.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Tools don't appear in chat | Hermes loads plugin tools at session start | Start a new session / restart the desktop app |
| `tone-forge` missing from `hermes plugins list` | Wrong directory depth | Manifest must sit at `plugins/tone-forge/plugin.yaml` |
| `no MIDI backend is available` | Not on Windows and `python-rtmidi` missing | Install `python-rtmidi`, or run on Windows with the built-in `winmm` backend |
| `no MIDI output ports exist` | loopMIDI not running or no port created | Start loopMIDI, add a port, restart AmpliTube |
| Only "Microsoft GS Wavetable Synth" listed | No virtual loopback installed | Install loopMIDI |
| `ToneForge never sends to a port you did not choose` | No port selected | `toneforge_select_midi_port` |
| `has no MIDI mapping` | Mapping table empty | Assign the CC in AmpliTube, then `toneforge_map_parameter` |
| Message sent, AmpliTube does nothing | Wrong MIDI input, wrong channel, or the assignment is on another preset | Check Settings → Audio/MIDI and Settings → Control; confirm the preset |
| Knob only moves halfway | AmpliTube Min/Max is not 0%/100% | Set `param_max` accordingly, or reset Min/Max in AmpliTube |
| Knob moves backwards | Reversed control | Record the mapping with `invert: true` |
| `device already allocated` | Another app holds the port exclusively | Close it, or restart loopMIDI |
| `python-rtmidi` will not install | No wheel for your CPython | Not required on Windows — use the built-in `winmm` backend |
| New plugin code seems ignored | The running gateway keeps previous modules in memory | Restart the desktop app or run `hermes gateway restart` |

More: [`docs/MIDI_SETUP_WINDOWS.md`](docs/MIDI_SETUP_WINDOWS.md) and [`docs/INSTALLATION_WINDOWS.md`](docs/INSTALLATION_WINDOWS.md).

---

## Limitations

- **No native `.at5p` presets.** The format is undocumented; ToneForge will not fabricate a file AmpliTube might reject. Presets are JSON recipes.
- **No model insertion.** AmpliTube exposes no scripting/remote API for building a chain; the recipe is applied by hand.
- **Mapping is user-owned.** ToneForge cannot discover which CC you assigned; you tell it. That is a deliberate design choice, not a missing feature.
- **MIDI reception is unverifiable from inside a plugin.** `applied: "unverified"` is the accurate answer.
- **Preset-scope assignments.** Amp-knob CCs in AmpliTube are per-preset; drive several presets only after assigning the CCs in each.
- **Single-machine, offline.** No cloud tone exchange, no ToneNET integration.
- **`python-rtmidi` is optional, not bundled** — the `winmm` backend exists precisely because that package has no wheel for every Python version.
- **Reference names are inspiration, not reproduction.** Artist and song names describe a tonal direction; ToneForge does not claim to recreate a recording.

---

## Roadmap

- Per-preset mapping sets (`mapping profile` keyed by AmpliTube preset name) so one library can drive many presets.
- A `toneforge_export` command that prints a human-readable setup sheet (Markdown) for the pedalboard.
- Program Change support for preset switching (AmpliTube accepts PC, per the manual).
- Optional audio-side sanity check: render a DI clip through the user's own chain and compare spectra — only if it can be done without shipping an audio engine.
- A `/tone` slash command that shows the current preset and MIDI readiness in one line.

---

## Screenshots and demo

No screenshots or recordings are committed yet. When they exist, they will be real captures of the plugin running in Hermes — not mock-ups. Planned placeholders:

| Asset | Shows |
|---|---|
| `docs/assets/hermes-create-preset.png` | Hermes chat with a full `toneforge_create_preset` response |
| `docs/assets/hermes-adjust-preset.png` | Before/after change list from `toneforge_adjust_preset` |
| `docs/assets/amplitube-midi-learn.png` | AmpliTube 5 MIDI Learn dialog with a CC assigned |
| `docs/assets/demo.mp4` | 90-second walkthrough from prompt to moving knob |

The recording plan, narration, shot list and failure-recovery notes are in [`docs/DEMO_SCRIPT.md`](docs/DEMO_SCRIPT.md). Do not add staged screenshots; capture the real UI state.

---

## Development

```bash
python -m unittest discover -s tests -v          # unit suite (139 tests, no hardware)
python scripts/live_midi_check.py                # real winmm MIDI egress (Windows)
python scripts/test_amplitube.py loopback        # proves the loopMIDI cable end to end
python scripts/test_amplitube.py sweep           # moves a mapped knob so you can watch it
hermes plugins doctor . --ci                     # real registration check
hermes plugins validate .                        # catalog-grade validation
```

Layout: `__init__.py` (registration) · `schemas.py` (model-facing) · `tools.py` (handlers) · `tone_engine.py` · `tone_profiles.py` · `preset_store.py` · `midi_io.py` · `midi_map.py` · `validation.py` · `tests/` · `docs/`.

CI runs the same unit suite on Windows and Linux across supported Python versions on pushes to `main` and on pull requests: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Additional documentation:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — design decisions, data flow, error model, security posture.
- [`docs/FEASIBILITY.md`](docs/FEASIBILITY.md) — platform and API constraints.
- [`docs/INSTALLATION_WINDOWS.md`](docs/INSTALLATION_WINDOWS.md) — install, update, uninstall.
- [`docs/MIDI_SETUP_WINDOWS.md`](docs/MIDI_SETUP_WINDOWS.md) — loopMIDI and AmpliTube setup.
- [`docs/EXAMPLE_PROMPTS.md`](docs/EXAMPLE_PROMPTS.md) — prompts, tool calls, refusal cases.
- [`CHANGELOG.md`](CHANGELOG.md) — release history.

## License

MIT — see [LICENSE](LICENSE).

AmpliTube, IK Multimedia and related marks belong to IK Multimedia. ToneForge is an independent project, not affiliated with or endorsed by IK Multimedia. Artist and song names are used only to describe tonal inspiration.
