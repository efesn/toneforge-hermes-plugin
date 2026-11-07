# MIDI setup on Windows (AmpliTube 5 Standalone + loopMIDI)

The goal: a cable that exists only in software, from ToneForge (inside Hermes) to
AmpliTube 5.

```text
Hermes + ToneForge ──CC──► loopMIDI port "ToneForge" ──► AmpliTube 5 (MIDI Input)
```

AmpliTube only reacts to **Control Change** and **Program Change** messages
(note numbers, aftertouch and pitch bend are ignored), and only to CCs **you
assigned inside AmpliTube**. Everything below follows the official AmpliTube 5
manual, chapter 5 ("MIDI Control") and chapter 2.2 ("Audio MIDI Setup").

---

## Part A — create the loopback port (loopMIDI)

1. Install **loopMIDI** from <https://www.tobias-erichsen.de/software/loopmidi.html>.
2. Launch it. It lives in the notification area (system tray) and must stay running.
3. In the **New port-name** field type `ToneForge`, click **+**.
4. The port now appears in the list and is visible to every MIDI application.

Verify from Hermes:

> List my MIDI ports.

`toneforge_list_midi_ports` should show `ToneForge` with `looks_like_loopback: true`.
If it does not appear, restart loopMIDI, then re-run the tool — the port list is
queried live, but Windows sometimes needs a second to register a new port.

---

## Part B — point AmpliTube at the port

AmpliTube 5 **Standalone** needs to be told which MIDI input to read.

1. Open **Settings → Audio/MIDI** (the button in the Top Bar).
2. **MIDI input**: select `ToneForge`. (`Any` also works, but a specific port is
   less surprising — only that port's messages reach AmpliTube.)
3. Apply/OK.

Then set the channel:

4. **Settings → Control → Control Change**.
5. Check the **MIDI Channel** display (click and scroll, 1-16). It must match
   ToneForge's channel — ToneForge defaults to **1**.
6. Leave **Min/Max** at `0%` / `100%` and **Curve** at `5` (linear). ToneForge
   assumes a linear 1:1 mapping of CC travel to parameter travel; a different
   Min/Max percentage is fine as long as you record it (`param_max`) — see Part D.

> AmpliTube can read from a plugin host's MIDI stream when it runs as a plug-in.
> This guide is for **Standalone**, which is what ToneForge targets.

---

## Part C — assign a CC to a knob inside AmpliTube

Two equivalent routes; use whichever you find faster.

### Route 1 — right-click (fast, one parameter)

1. Right-click the knob (e.g. the amp's **Gain**).
2. **Assign MIDI → [parameter name] → Learn [parameter name]**.
3. AmpliTube now waits for a CC. Send one from Hermes:

   > Probe CC 20 so AmpliTube learns it.

   (`toneforge_midi_probe` with `cc: 20` sends `0 → 127 → 64`, which is exactly
   what a hardware knob sweep looks like to AmpliTube.)
4. The assignment is applied. The final value leaves the knob at 64/127 ≈ 50%.

### Route 2 — the MIDI Control panel (precise, batch)

1. **Settings → Control** (top-right button in the settings window).
2. **Control Change → Preset** (or **Global** — see the scope note below).
3. **Add** → pick the parameter from the tree → select it → **Learn**.
4. Send the CC from Hermes (`toneforge_midi_probe`).
5. **OK** to save, **Cancel** to discard. **Clear** / **Clear All** remove
   assignments.

### Scope: why this matters

| Scope | What it can control | When it applies |
|---|---|---|
| **Global** | preset next/previous, volume pedal, wah, wharmonator, the 12 stomp bypasses | every preset |
| **Preset** | any parameter — amp gain, bass, mid, treble, presence, pedal knobs, rack | **only the current preset** |

Amp knobs are therefore **Preset** assignments. If ToneForge moves the gain on
preset A and nothing happens on preset B, that is not a bug — assign the CC again
on preset B, or use Global only for the controls listed above.

ToneForge records the scope with every mapping and reminds you when a mapping is
preset-scoped.

---

## Part D — teach ToneForge the mapping

ToneForge does not guess. After you have assigned a CC in AmpliTube, record it:

> Map amp gain to CC 20.

```json
toneforge_map_parameter({"parameter": "amp_gain", "cc": 20, "channel": 1, "scope": "preset"})
```

Then drive it:

> Set the amp gain to 80.

```json
toneforge_set_parameter({"parameter": "amp_gain", "value": 80})
→ "value": 102, "bytes_hex": "B0 14 66", "applied": "unverified"
```

`80/100 → CC 102` is the linear conversion. `applied: "unverified"` is deliberate:
Windows accepted the bytes, but only AmpliTube can show whether the knob moved.

### Range and inversion

| AmpliTube setting | ToneForge mapping |
|---|---|
| Min 0% / Max 100% (default) | `param_min: 0, param_max: 100, invert: false` |
| Min 0% / Max 50% | `param_max: 50` |
| Min 100% / Max 0% (reversed control) | `invert: true` |

ToneForge's `min`/`max` are **raw CC bytes** (0-127); `param_min`/`param_max` are
the parameter's own units. Keep them distinct and the conversion stays exact.

### Suggested CC layout

ToneForge ships a *convention* (not an AmpliTube default) that avoids CC 0-19 and
64/120-127, which are common footswitch/global controls:

| CC | Parameter | CC | Parameter |
|---|---|---|---|
| 20 | `amp_gain` | 28 | `od_drive` |
| 21 | `amp_bass` | 29 | `od_level` |
| 22 | `amp_mid` | 30 | `od_tone` |
| 23 | `amp_treble` | 31 | `delay_mix` |
| 24 | `amp_presence` | 32 | `reverb_mix` |
| 25 | `amp_master` | | |
| 26 | `gate_threshold` | | |
| 27 | `gate_decay` | | |

Install it in one call (`toneforge_map_parameter` with `seed_suggested: true`),
then assign the same CCs in AmpliTube. A seeded mapping is flagged
`mapping_source: "toneforge-convention"` and every `set_parameter` call on it
carries a warning until you replace it with a real assignment.

---

## Part E — verification checklist

Work down this list once; after that the bridge is dependable.

- [ ] `toneforge_midi_status` → `active_backend: "winmm"` (or `rtmidi`), `ports_available ≥ 1`
- [ ] `toneforge_list_midi_ports` → `ToneForge` present, `looks_like_loopback: true`
- [ ] `toneforge_select_midi_port` → `ToneForge` selected
- [ ] AmpliTube: Settings → Audio/MIDI → MIDI input = `ToneForge`
- [ ] AmpliTube: Settings → Control → MIDI Channel = same as ToneForge (1)
- [ ] AmpliTube: a knob has the CC assigned (right-click → Assign MIDI → Learn)
- [ ] `toneforge_map_parameter` with that exact CC
- [ ] `toneforge_set_parameter` → `sent: true`, and **the knob in AmpliTube moves**
- [ ] `toneforge_midi_status` → `ready: true`

If the knob does not move, the plugin is not the suspect — the last three rows
are the ones that involve AmpliTube's own settings.

### Run the whole thing from one script

`scripts/test_amplitube.py` drives the plugin exactly as the agent would, so you can
separate "my plugin is broken" from "AmpliTube is not listening" in seconds:

```bash
cd "$HERMES_HOME/plugins/tone-forge"

python scripts/test_amplitube.py status      # backend, ports, selection, blockers
python scripts/test_amplitube.py loopback    # proves the cable WITHOUT AmpliTube
python scripts/test_amplitube.py learn       # sends 0→127→64 so you can complete Learn
python scripts/test_amplitube.py sweep       # 0→127→0 slowly: watch the knob travel
python scripts/test_amplitube.py set 80      # land on 80/100 and print the bytes
```

`loopback` opens the loopback port as a MIDI **input**, sends one CC through the
plugin, and checks the exact bytes arrive back:

```text
  → sending to: ToneForge
  opening input [0] ToneForge
  sent: B0 14 60
  received: status 0xB0, data1 20, data2 96
  ✓ the virtual cable delivers the exact bytes ToneForge sent.
```

When that passes, the cable, the backend, the port selection and the conversion
are all proven. Anything still not moving is AmpliTube configuration — work the
checklist above.

---

## Part F — troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ToneForge` not in the port list | loopMIDI not running / port not created | start loopMIDI, add the port, re-list |
| Port list shows only "Microsoft GS Wavetable Synth" | no loopback installed | install loopMIDI (that device is a synth, not a cable) |
| `no MIDI output port is selected` | selection never made | `toneforge_select_midi_port` |
| `the selected port … is no longer available` | port renamed/removed | re-list and select again; ToneForge will not silently fall back |
| AmpliTube shows no MIDI input | port created after AmpliTube started | restart AmpliTube |
| Message sent, nothing moves | wrong MIDI input in AmpliTube | Settings → Audio/MIDI → pick `ToneForge` |
| Message sent, nothing moves (input is right) | channel mismatch | Settings → Control → MIDI Channel = ToneForge channel |
| Some knobs move, others do not | those knobs have no assignment on this preset | assign them (Part C), remember **Preset** scope |
| Knob jumps to min/max only | AmpliTube mapped a switch with **Latch** on | turn Latch off for continuous parameters |
| Knob only travels half range | AmpliTube Min/Max not 0/100% | record `param_max` (e.g. 50) or reset Min/Max |
| Knob moves backwards | reversed control | `invert: true` (AmpliTube Min 100% / Max 0%) |
| Nothing listens to note/aftertouch/pitch bend | AmpliTube supports CC and PC only | use CC |
| `device already allocated` | another app holds the port exclusively | close it, or restart loopMIDI |

### What ToneForge cannot diagnose for you

- Whether AmpliTube applied a message (no state read-back in AmpliTube's MIDI implementation).
- Which CC you assigned (it is stored inside AmpliTube's preset, not exposed).
- Whether the amp model you picked in AmpliTube matches the recipe (different
  models respond differently to the same knob positions — that is why ToneForge
  describes families and lets you pick the closest model).
