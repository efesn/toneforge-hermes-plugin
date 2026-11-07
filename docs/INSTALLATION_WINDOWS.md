# Installing ToneForge on Windows

Tested on Windows 11 with Hermes Agent v0.23.0 (git install), Python 3.14.9,
AmpliTube 5 at `C:\Program Files\IK Multimedia\AmpliTube 5`.

---

## 0. Prerequisites

| Requirement | Check |
|---|---|
| Hermes Agent ≥ 0.23.0 | `hermes --version` |
| A Python the Hermes install can import (`3.10+`) | `hermes doctor` (Hermes ships its own interpreter) |
| AmpliTube 5 (Standalone) | Launch it once so its settings exist |
| loopMIDI (only for the MIDI bridge) | <https://www.tobias-erichsen.de/software/loopmidi.html> |

ToneForge has **no Python dependencies**. Nothing needs `pip install`.

---

## 1. Find your Hermes home

```bash
echo "$HERMES_HOME"
```

Typical values:

- default Windows install → `C:\Users\<you>\AppData\Local\hermes`
- classic layout → `C:\Users\<you>\.hermes`

Every path below uses `$HERMES_HOME`. If the variable is empty, use
`C:\Users\<you>\AppData\Local\hermes` (that is what this machine uses).

---

## 2. Copy the plugin into place

The plugin directory must be **exactly one level deep** — `plugins/<name>/plugin.yaml`.
Deeper nesting is silently ignored by the loader.

```bash
mkdir -p "$HERMES_HOME/plugins"
cp -r "/c/Users/<you>/Desktop/tone-forge" "$HERMES_HOME/plugins/tone-forge"
```

Check the shape:

```bash
ls "$HERMES_HOME/plugins/tone-forge"
# __init__.py  plugin.yaml  schemas.py  tools.py  ...
```

> Published as a Git repository instead? `hermes plugins install owner/tone-forge`
> does the same thing through the installer and records provenance. A local
> `cp -r` is tracked as a user plugin without provenance, which is fine.

---

## 3. Enable it

```bash
hermes plugins enable tone-forge
```

Plugins are opt-in. Expected output:

```text
✓ Plugin tone-forge enabled.
Gateway reloaded plugins — deferred: tools (next session).
```

The `deferred: tools (next session)` line is normal: tools are attached when a
session starts.

---

## 4. Verify the install

```bash
# 15 structural checks: manifest, loadability, declared tools, security scan, ...
hermes plugins validate "$HERMES_HOME/plugins/tone-forge"

# real discovery + import + register(ctx) in an isolated HERMES_HOME
hermes plugins doctor "$HERMES_HOME/plugins/tone-forge" --ci

# is it listed and enabled?
hermes plugins show tone-forge
```

Expected:

```text
✓ declared tools — matches registrations
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
Validation passed.

Plugin Doctor: ...\tone-forge
  manifest: tone-forge 1.0.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 17 tool(s), 0 hook(s)
```

Reference analysis additionally needs `ffmpeg` on PATH (and `yt-dlp` if you want to pass URLs);
both are optional and every other tool works without them.

Then run the unit suite (no hardware required):

```bash
cd "$HERMES_HOME/plugins/tone-forge"
python -m unittest discover -s tests
# Ran 149 tests ... OK
```

---

## 5. First session

Restart the Hermes desktop app (or start a new `hermes` session) so the tool list
is rebuilt, then ask:

> Use ToneForge to create an industrial metal tone for Drop D with a tight low end.

You should see `toneforge_create_preset` in the tool list:

```bash
hermes plugins list | grep tone-forge
```

---

## 6. Settings

Two settings live under `plugins.entries.tone-forge.settings` in `config.yaml`
(and render as a form in **Settings → Plugins** in the desktop app):

| Key | Default | Meaning |
|---|---|---|
| `midi_backend` | `auto` | `auto` = rtmidi when importable, else the stdlib `winmm` driver |
| `default_channel` | `1` | MIDI channel 1-16 used when a call does not name one |

Change them with the CLI rather than by editing YAML:

```bash
hermes config set plugins.entries.tone-forge.settings.default_channel 1
```

---

## 7. Data locations

| What | Path |
|---|---|
| Presets | `$HERMES_HOME/plugin-data/tone-forge/presets/*.json` |
| MIDI mappings | `$HERMES_HOME/plugin-data/tone-forge/midi_map.json` |
| Selected port | `$HERMES_HOME/plugin-data/tone-forge/midi_config.json` |

This directory survives `hermes plugins update` and `hermes plugins remove` by
design (it is the sanctioned per-plugin data root, not the install tree).

Back up your library with a plain copy:

```bash
cp -r "$HERMES_HOME/plugin-data/tone-forge/presets" ~/toneforge-backup
```

---

## 8. Update

```bash
# if installed from git
hermes plugins update tone-forge

# if installed by copying
cp -r "/c/Users/<you>/Desktop/tone-forge/." "$HERMES_HOME/plugins/tone-forge/"
hermes plugins list   # version check
```

Restart the session afterwards — tool schemas are read at startup.

---

## 9. Uninstall

```bash
hermes plugins disable tone-forge          # keep files, hide tools
hermes plugins remove  tone-forge          # delete the install tree
rm -rf "$HERMES_HOME/plugin-data/tone-forge"   # optional: delete presets + mappings
```

`remove` does **not** delete your presets; that last line does.

---

## 10. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `tone-forge` missing from `hermes plugins list` | wrong directory depth (`plugins/x/tone-forge/…`) | the manifest must sit at `plugins/tone-forge/plugin.yaml` |
| Listed but tools absent | session started before enabling | restart the desktop app / new session |
| `Plugin tone-forge disabled (missing: …)` | a `requires_env` entry is unset | ToneForge declares none — check you copied the shipped manifest |
| `validate` fails "declared tools — mismatch" | manifest edited without updating `register()` | keep `provides_tools` and `TOOLS`/`HANDLERS` in sync |
| `register()` failed in doctor | import error (e.g. a module renamed) | run `HERMES_PLUGINS_DEBUG=1 hermes plugins list` for the traceback |
| Tools listed but every MIDI call errors | no backend / no port | see [`MIDI_SETUP_WINDOWS.md`](MIDI_SETUP_WINDOWS.md) |
| Behaviour does not match the code you just installed | the running gateway keeps the previous plugin modules in its plugin-host child | restart the desktop app / gateway (see below) |
| `hermes plugins validate` says "not a directory" | run from inside the plugin dir with a bare name | pass a path: `hermes plugins validate ./tone-forge` |
| Tools vanish after a config edit | YAML corruption | `hermes config get plugins.entries.tone-forge` and fix via `hermes config set` |

Useful diagnostics:

```bash
HERMES_PLUGINS_DEBUG=1 hermes plugins list      # discovery + per-plugin load reasons
hermes logs --level WARNING | grep -i toneforge # runtime errors from the plugin
```

Note: this profile runs plugins in the **plugin host** (`plugins.isolation: host`),
i.e. a per-profile subprocess. If you see a host-startup error in the logs, the
plugin itself still validates — check `hermes plugins doctor` output first.

### After updating the plugin, the old behaviour persists

The gateway (and its plugin-host child) loads plugin modules **once** and keeps
them in memory. Copying new files over an install that a running gateway already
loaded changes nothing inside that process — `hermes plugins list` shows the new
version while the tools still behave like the old one.

Observed on this machine: the plugin host had started at 02:00, the synced copy
landed at 02:01, and a `hermes chat -q` call at 02:02 still produced the previous
release's output. A fresh import of the installed directory produced the new
behaviour, which isolates the cause to the running process, not to the files.

Fix: restart the surface that owns the process.

```bash
hermes gateway restart        # or: quit and reopen the desktop app
hermes plugins list           # version check
```

Verify which copy is loaded if you are unsure:

```bash
cd "$HERMES_HOME/plugins/tone-forge" && python -c "import tone_engine; print(tone_engine.__file__)"
```
