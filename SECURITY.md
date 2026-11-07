# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.x | Yes |

## Reporting a vulnerability

Please report security issues privately through GitHub's **Security → Advisories → Report a vulnerability** flow on this repository. Do not open a public issue for a vulnerability before it has been assessed.

Include:

- The affected version or commit.
- A minimal reproduction (tool call, preset file, mapping file, or script).
- The impact you believe it has.

You can expect an acknowledgement within a few days. This is a small, single-maintainer project; there is no paid bug-bounty program.

## Security design

ToneForge is a local Hermes Agent plugin. It is designed to run with the least capability the task needs:

- **No network access of its own.** No HTTP client, no telemetry, no update check, no cloud tone
  service. The only outbound traffic is `yt-dlp`, and only when a tool call passes an explicit `url`.
- **No arbitrary process execution.** `os.system`, `eval`, `exec` and dynamic imports of
  user-controlled strings are absent. Reference analysis is the single `subprocess` user: `ffmpeg`
  to decode audio, plus `yt-dlp` when a `url` is given - fixed argv, no shell, bounded timeout.
- **Audio stays local.** A reference file is decoded from disk; a URL download lands in a temporary
  directory that is deleted when the call returns. No audio is copied into the preset library.
- **No credential handling.** The plugin does not read, store, log, or transmit tokens, passwords, or API keys.
- **Bounded filesystem writes.** Presets, MIDI mappings and MIDI configuration live under `<HERMES_HOME>/plugin-data/tone-forge/`. Writes use a temporary file in the same directory, `fsync`, and `os.replace`.
- **Path-traversal protection.** Slugs are validated against `^[a-z0-9][a-z0-9._-]{0,63}$`, rejected if they contain `..` or a leading dot, and the resolved parent directory must equal the store root before any path is built.
- **Input validation.** Ranges, types, channel (1-16), CC (0-127) and value (0-127) are checked before any backend call.
- **Explicit MIDI egress only.** ToneForge never sends to a port the user did not select and never guesses a CC assignment. A vanished port raises instead of falling back to another device.
- **No AmpliTube file modification.** The plugin never writes to AmpliTube's preset directory or any IK Multimedia file.
- **Atomic, size-capped storage.** Presets larger than 1 MB, non-JSON files, and files with a future schema version are refused.

The unit test suite covers path traversal, invalid ranges, missing or stale port selection, backend failure, atomic writes and the "never send without a selection" rule. See `tests/` and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
