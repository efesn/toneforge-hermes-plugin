# Changelog

All notable changes to ToneForge are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] — 2026-11-07

Reference-track analysis: build a tone from what a recording actually measures instead
of from a genre profile's prior.

### Added
- `toneforge_analyze_reference`: local file or URL (yt-dlp) -> octave and third-octave
  balance, spectral slope, 95% rolloff, low-frequency tuning peaks, decay tail and stereo
  width, then a complete recipe whose numbers come from the audio.
- `reference_analysis.py`: `ffmpeg`-decoded analysis with a pure-Python radix-2 FFT, so the
  plugin still needs no third-party Python packages.
- `tone_engine.apply_overrides()`: writes measured params/EQ/gate/space (and a measured
  amp/cab family hint) into a normal recipe, keeping the provenance.
- `tests/test_reference.py`: synthetic `ffmpeg` fixtures, 10 tests.

### Changed
- A measured recipe replaces the profile's canned `why` lines with the measurements plus one
  line naming what the profile still contributed (families and structure).
- Low-string peaks are measured with a 16384-point FFT: at 16 kHz a 4096-point bin is ~90
  cents at 74 Hz, which cannot tell D from Eb.
- A decay longer than half the analysed window is treated as a clip fade, never as reverb;
  the tail falls back to the last 25 s of the track when the window never decays.

## [1.0.0] — 2026-11-07

First release. Targets Hermes Agent ≥ 0.23.0 (plugin API: `plugin.yaml` +
`register(ctx)`), Windows 10/11, AmpliTube 5 Standalone.

### Added — tone design
- `toneforge_create_preset`: genre/reference/tuning/pickup/purpose/gain/instructions →
  complete recipe (signal chain, amp + cab + mic, pedals, 7-band EQ, gate, levels,
  post-processing, rationale, assumptions, disclaimer).
- Nine profiles: Industrial Metal, Modern Metal, Thrash Metal, Metalcore, Hard Rock,
  Classic Rock, Clean, Ambient, Lead/Solo.
- Ten tunings with compensation (bass trim, high-pass, gate, presence): standard,
  Eb, D standard, Drop D, Drop C, C standard, Drop B, B standard/7-string, Drop A.
- Six pickup models with gain/treble/bass bias and noise-aware gating.
- Six purposes with gain caps (rhythm, lead, solo, clean, ambient, crunch).
- `toneforge_adjust_preset`: natural-language adjustment with a precise
  `{field, before, after}` change list, without mutating the stored preset.
- 25 instruction modifiers in English and Turkish, plus `N up/down` and
  `set <param> to N` overrides applied last.
- `toneforge_list_profiles`.

### Added — preset library
- `toneforge_save_preset`, `toneforge_list_presets`, `toneforge_get_preset`,
  `toneforge_delete_preset`.
- JSON preset schema with `schema_version`, slug, version counter, timestamps, notes.
- Atomic writes (temp file + `os.replace` + `fsync`), overwrite protection,
  confirm-gated deletion, slug/path-traversal validation, 1 MB size cap,
  future-schema refusal.

### Added — MIDI bridge
- `toneforge_midi_status`, `toneforge_list_midi_ports`, `toneforge_select_midi_port`,
  `toneforge_send_midi`, `toneforge_set_parameter`, `toneforge_map_parameter`,
  `toneforge_list_mappings`, `toneforge_remove_mapping`, `toneforge_midi_probe`.
- Two backends behind one interface: `winmm` via `ctypes` (standard library, no
  dependency) and optional `python-rtmidi`.
- Explicit port selection persisted in `midi_config.json`; a vanished port raises
  instead of falling back.
- User-owned CC mappings with channel (1-16), CC range (0-127), parameter range,
  inversion and AmpliTube scope (`preset`/`global`).
- Linear value conversion, `bytes_hex` reporting, and an explicit
  `applied: "unverified"` result.

### Added — engineering
- 16 tools with strict schemas and JSON-string handlers that never raise.
- 139 unit tests: validation, tone engine, storage, mapping, MIDI (mocked hardware),
  handler contract. No device, no AmpliTube, no network.
- `scripts/live_midi_check.py` for real Windows MIDI egress.
- Documentation: README, feasibility report, Windows installation, MIDI setup,
  architecture, example prompts, demo script, hackathon material.

### Verified
- `hermes plugins validate` → 15/15 checks pass.
- `hermes plugins doctor --ci` → runtime discovery, import and registration OK,
  16 tools.
- Live MIDI: `B0 14 66` (CC 20 = 102, channel 1) sent through `winmm`, return code 0.

### Known limitations
- No native AmpliTube `.at5p` support (undocumented format; never fabricated).
- No model insertion or chain building inside AmpliTube (no scripting surface).
- AmpliTube parameter CCs are per-preset assignments; ToneForge records the scope
  but cannot re-assign them for you.
- AmpliTube reception cannot be confirmed from inside a plugin.
- `python-rtmidi` is optional and may lack a wheel for very new CPython releases
  (the `winmm` backend exists for exactly that case).
