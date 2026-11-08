# Add tone-forge plugin

ToneForge is an AI guitar tone engineer for IK Multimedia AmpliTube 5 inside Hermes Agent.
A plain-language request ("industrial metal for Drop D, tight low end, Rammstein-ish") becomes
a complete, explained tone recipe: ordered signal chain, amp/cabinet families with browser
search terms, mic placement, pedal settings, 7-band EQ, noise gate, and normalised
gain/bass/mid/treble/presence/master — plus a `why` line for every decision and explicit
assumptions wherever the request was silent.

Since 1.1 it can also work from a real recording: `toneforge_analyze_reference` decodes a
local file (or a URL, via yt-dlp) with ffmpeg, runs its own FFT, measures octave and
third-octave balance, spectral slope, 95% rolloff, low-frequency tuning peaks, decay tail and
stereo width, then writes those numbers into the recipe with the provenance kept per value.
It states up front that it measures the **mix**, not an isolated guitar stem.

## Hermes surfaces used

- `ctx.register_tool` — 17 tools on toolset `toneforge`, strict JSON schemas, handlers that
  return JSON strings and never raise.
- `config_schema` — `midi_backend` (`auto`/`winmm`/`rtmidi`) and `default_channel` (1–16).
- Plugin data dir (`plugin-data/tone-forge/`) for the JSON preset library and MIDI mappings.
  The plugin never writes to AmpliTube's own files.

No hooks, no middleware, no Desktop surface, no core imports or overrides.

## Disclosure (rule 13)

- **Subprocess:** `reference_analysis` spawns `ffmpeg` to decode audio, and `yt-dlp` **only**
  when a tool call passes an explicit `url`. Fixed argv, no shell, bounded timeouts.
- **Network:** no HTTP client in the plugin. The only outbound traffic is `yt-dlp` in that
  same opt-in path; downloads land in a temporary directory that is deleted when the call
  returns.
- **Filesystem:** writes only under `HERMES_HOME/plugin-data/tone-forge/`.
- **MIDI:** sends CCs only to a port the user selected explicitly; never guesses a port or a
  CC mapping.
- **Platform:** validated on Windows 11 with AmpliTube 5 Standalone; `platforms: [windows]`
  because the built-in MIDI backend is `winmm` (python-rtmidi is optional).

## Verification on the pinned tree

- `python -m unittest discover -s tests` → 162 tests, OK (1 skipped: rtmidi not installed)
- `hermes plugins validate ./tone-forge` → Validation passed (15 checks)
- `hermes plugins doctor ./tone-forge --ci` → 17 tool(s), 0 hook(s)
- `scripts/live_midi_check.py` → a real CC (`B0 14 66`) left the machine through `winmm`

## What is not claimed

AmpliTube receiving MIDI is documented but not demonstrated on the build machine (no
loopback port installed). Native `.at5p` writing is deliberately out of scope. Model
availability differs per edition, so profiles describe families and search terms, never
"this model exists in your edition".
