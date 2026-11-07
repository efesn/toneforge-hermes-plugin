# Architecture

## Why the code looks like this

Three constraints drove every structural decision:

1. **Hermes loads a plugin as a package** (`__init__.py` with sibling modules
   registered as `plugin.<stem>`), so modules must import each other relatively
   (`from . import midi_io`). Plain `import midi_io` only works if the plugin
   directory happens to be on `sys.path`, which it is not.
2. **Tool handlers must never raise and must return JSON strings.** All error
   handling is therefore centralised in one decorator, and the domain layer is
   free to raise typed exceptions with human-readable messages.
3. **The MIDI bridge must work on a machine with no third-party packages.** The
   `winmm` backend is written against `ctypes`; `python-rtmidi` is a bonus, not
   a requirement.

## Module map

| Module | Responsibility | Depends on |
|---|---|---|
| `__init__.py` | `register(ctx)`: read settings, register 17 tools | `schemas`, `tools` |
| `schemas.py` | Tool schemas and descriptions — the model-facing surface | stdlib |
| `tools.py` | Handlers: validate args → call domain → JSON envelope | all domain modules |
| `tone_engine.py` | Resolve genre, apply tuning/pickup/purpose, instruction modifiers, render chain, diff adjustments | `tone_profiles`, `validation` |
| `tone_profiles.py` | Data: 10 tunings, 6 pickups, 6 purposes, 9 profiles, chain order, disclaimer | stdlib |
| `preset_store.py` | JSON preset library: slugs, atomic writes, versioning, listing | `validation`, optional `plugins.plugin_storage` |
| `reference_analysis.py` | Reference-track measurement (`ffmpeg` decode + pure-Python FFT) and the mapping from measurements to tone overrides | `validation` |
| `midi_map.py` | User CC mapping table + value conversion | `validation` |
| `midi_io.py` | Backends (`winmm`, `rtmidi`), port selection, send, probe | `validation` |
| `validation.py` | Ranges, text hygiene, slugs, path safety, error types | stdlib |

No module imports `hermes_cli`, `agent`, `tools.registry` or any other core
internal. The only host import is `plugins.plugin_storage.plugin_data_dir`,
guarded so the suite runs outside Hermes.

## Data flow — creating a tone

```text
tools.create_preset(args)
  ├─ coerce gain_level (0-100)                       validation.coerce_int
  ├─ tone_engine.build_tone(...)
  │    ├─ resolve_genre(genre, reference)            exact key → alias → token overlap → fallback
  │    ├─ normalize tuning / pickup / purpose        alias tables
  │    ├─ copy profile params
  │    ├─ _apply_tuning     bass↓ presence↑ high-pass, gate tighter
  │    ├─ _apply_pickup     gain/treble/bass bias, gate tighter for noisy pickups
  │    ├─ _apply_purpose    param deltas + gain cap + gate/space policy
  │    ├─ apply_instructions  ordered modifiers, one per family, then numeric overrides
  │    └─ render_signal_chain  fixed CHAIN_ORDER skeleton, optional stages only if present
  └─ JSON: {tone, applies_automatically: false, how_to_apply, next_steps}
```

**Determinism** is a feature: no RNG, no clock, no network. The same request
returns the same recipe, which is what makes a stored preset reproducible and
the tests assertable.

### Why instruction modifiers are "one per family"

`"remove the noise gate"` matches both the gate-off rule and the catch-all
`\bgate\b` rule. A naive ordered loop disabled the gate and then immediately
re-enabled it. Modifiers are therefore tagged with a family (`gate`, `tight`,
`low`, `mid`, `gain`, …) and the first match per family wins, in a fixed order:
gate/space intent first, then tone shaping, then gain, then explicit numbers
last. `"set gain to 75"` always beats the adjective in the same sentence.

### Why purposes cap gain instead of subtracting it

A fixed `-40` gain delta cleans up a high-gain profile but starves an already
clean one (`18 - 40 → 0`). Purposes therefore carry an optional `gain_cap`
(`clean: 30`, `ambient: 34`, `crunch: 55`) and only nudge the tone stack.
`metalcore + clean` lands at 30; `clean + ambient` keeps its 18.

## Data flow — adjusting a tone

```text
tools.adjust_preset(args)
  ├─ base = args.config  or  preset_store.load(args.preset).config
  ├─ tone_engine.adjust_tone(base, instructions, gain_level?, purpose?, tuning?)
  │    ├─ deep-copy (the stored preset is never mutated)
  │    ├─ optional re-tune / purpose switch / gain override
  │    ├─ apply_instructions
  │    ├─ re-render signal chain
  │    └─ diff(before, after) → [{field, before, after}]
  ├─ save only if save=true or save_as is set
  └─ JSON: {tone, changes, explanation, note: "stored preset was NOT modified"}
```

The `changes` list is the contract: it names the exact field, the old value and
the new value, so "make it tighter" is auditable rather than a vague claim.

## Preset format

```json
{
  "schema_version": 1,
  "slug": "industrial-metal-drop-d-rhythm",
  "name": "Industrial Metal - Drop D (rhythm)",
  "description": "Industrial Metal rhythm tone | inspired by ... | Drop D ...",
  "genre": "industrial_metal",
  "genre_label": "Industrial Metal",
  "reference": "Rammstein - Sonne",
  "tuning": "drop_d",
  "tuning_label": "Drop D (D A D G B e)",
  "pickup": "humbucker",
  "purpose": "rhythm",
  "notes": [],
  "config": { "amp": {}, "cabinet": {}, "mic": {}, "params": {}, "eq": {}, "gate": {}, "pedals": [], "space": {}, "signal_chain": [], "why": [], "post": [], "disclaimer": "..." },
  "version": 3,
  "created_at": "2026-11-07T02:10:00Z",
  "updated_at": "2026-11-07T02:41:12Z",
  "created_by": { "plugin": "tone-forge", "plugin_version": "1.0.0" },
  "disclaimer": "..."
}
```

Rules enforced by `preset_store`:

- `slug` is derived from the display name and re-validated (`^[a-z0-9][a-z0-9._-]{0,63}$`,
  no `..`, no leading dot) **before** any path is built; the resolved path's
  parent must equal the store root.
- Writes go to a temp file in the same directory, `fsync`, then `os.replace` — a
  crash cannot leave a half-written preset.
- Existing slugs are never replaced without `overwrite=true`; overwriting keeps
  `created_at` and increments `version`.
- Files over 1 MB, non-JSON files, and files with a newer `schema_version` are
  refused rather than guessed at.

## MIDI layer

```text
MidiService
 ├─ backend()            auto → rtmidi if importable else winmm
 ├─ list_ports()         per-call enumeration (devices can appear/disappear)
 ├─ select_port(...)     writes midi_config.json {backend, index, name}
 ├─ send_cc(...)         resolves target: explicit arg > saved selection > error
 └─ probe(...)           value sequence for MIDI Learn
```

**Safety properties, all covered by tests:**

- `send_cc` with no explicit port and no saved selection raises
  `MidiPortError("… ToneForge never sends to a port you did not choose.")`.
- A saved port that disappeared raises; it never falls back to "port 0".
- A failed `midiOutShortMsg` drops the cached handle and raises `MidiSendError`.
- Channel/CC/value are validated (1-16, 0-127, 0-127) before the backend is touched.
- Values are never sent on a guess: `set_parameter` requires a stored mapping.

**Conversion math** (`midi_map.to_cc`):

```text
ratio = (clamp(value, param_min, param_max) - param_min) / (param_max - param_min)
if invert: ratio = 1 - ratio
cc = round(min + ratio * (max - min))
```

So `80/100` with `min=0 max=127` → `round(0.8 * 127) = 102` → `B0 14 66`. This is
what the live check sent to a real Windows device.

### winmm details worth knowing

- `midiOutOpen` with `CALLBACK_NULL` (0) — no callback thread, no window handle.
- Handles are cached per device index: reopening on every message causes
  `MMSYSERR_ALLOCATED` on hardware that refuses a second open.
- `midiOutReset` + `midiOutClose` on shutdown, so no hanging notes are left behind.
- `midiOutGetDevCapsW` is called with the device index; the earlier probe that
  reported `0x7` (software synthesizer) confirms the technology mapping.

## Error model

| Exception | Meaning | Reaches the user as |
|---|---|---|
| `ValidationError` | bad argument (range, type, name) | `{"ok": false, "error": "...", "error_type": "ValidationError"}` |
| `NotFoundError` | unknown preset/mapping/port | same shape, actionable message |
| `ConflictError` | would overwrite existing data | same shape, names the existing record |
| `MidiUnavailable` | no backend at all | same shape + fix hint |
| `MidiPortError` | no/ambiguous/stale port | same shape, lists available ports |
| `MidiSendError` | backend refused the bytes | same shape with the Windows error name |
| anything else | a bug | logged with traceback, `{"ok": false, "error": "unexpected failure: …"}` |

## Security posture

- No `eval`, no `exec`, no dynamic `import` of user strings, no network client anywhere in the
  plugin. The single `subprocess` user is `reference_analysis` (`ffmpeg` to decode audio, and
  `yt-dlp` only when a tool call passes an explicit `url`); opt-in per call, fixed argv, no shell.
- Preset and mapping names are slugged and re-validated; traversal is tested
  (`../escape`, `..`, `/abs`, `a/b`).
- Writes are restricted to `<HERMES_HOME>/plugin-data/tone-forge/`.
- MIDI output requires an explicit selection or an explicit port argument on the
  very call that sends.
- Nothing is written to AmpliTube's own files; the plugin never touches
  `Documents/IK Multimedia/AmpliTube 5/`.

## Testing strategy

- `tests/_pkg.py` loads the plugin **the way Hermes does** (path-based package with
  `submodule_search_locations`), so a broken relative import fails the suite.
- MIDI is covered by a `FakeBackend` that records `(index, status, data1, data2)`;
  no device, no loopback, no AmpliTube.
- Storage tests use a temp directory and assert on real files (atomicity, no temp
  leftovers, corrupt-file handling).
- `scripts/live_midi_check.py` is the only hardware-touching test and is run
  manually.
