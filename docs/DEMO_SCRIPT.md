# 90-second demo script

Goal: show natural language → a real, explainable tone → a stored preset → a real
MIDI message leaving the machine. Record at 1080p, single window (Hermes desktop),
font size bumped one step, no dead air.

**Before recording**

- `hermes plugins list | grep tone-forge` shows `enabled`.
- loopMIDI running with a port named `ToneForge`; AmpliTube open with `ToneForge`
  as MIDI Input and a CC assigned to the amp gain knob (Part B/C of
  `MIDI_SETUP_WINDOWS.md`).
- Delete demo presets so the library looks clean: `toneforge_list_presets`.
- Have the chat scrolled to an empty session.

---

## 0:00–0:08 — the problem

**Say:** "AmpliTube sounds great, but turning 'I want a Rammstein-ish industrial tone'
into actual knob positions is a skill. ToneForge does that part."

**Show:** empty chat, one breath of the desktop app.

---

## 0:08–0:25 — create the tone

**Type:**

> Create a heavy industrial metal tone for Drop D, inspired by Rammstein's Sonne. Tight low end, controlled highs, keep note definition.

**Say (while it runs):** "One tool call — genre, reference, tuning, and three
plain-language constraints."

**Show:** `toneforge_create_preset` result. Point at three lines:

- the **signal chain** — gate → overdrive → amp → cab/mic → EQ → delay → reverb
- the **parameters** — gain 74, bass ~33, mid 65, presence 49
- the **explanation** — "bass is trimmed because Drop D already supplies weight"

---

## 0:25–0:38 — it explains itself

**Say:** "This is the part that matters: it does not just print numbers, it tells
you why. The overdrive is used as a filter, not a distortion. The presence sits
below the treble on purpose."

**Show:** scroll the `why` bullets once, slowly, then stop.

---

## 0:38–0:50 — adjust in conversation

**Type:**

> Make the low end tighter and add a bit more presence.

**Show:** `toneforge_adjust_preset` → the change list:

```text
params.bass        33 → 28
eq.low_cut_hz      92 → 102
eq.100hz           -4 → -6
params.presence    49 → 57
```

**Say:** "Before and after, field by field. And the stored preset is untouched
until I say save."

---

## 0:50–0:58 — save it

**Type:**

> Save it as "Sonne Rhythm".

**Show:** `toneforge_save_preset` → slug `sonne-rhythm`, version 1, path under
`plugin-data/tone-forge/presets/`.

**Say:** "A versioned JSON preset in the local library — not a fake `.at5p` file."

---

## 0:58–1:08 — MIDI status

**Type:**

> Is the MIDI bridge ready?

**Show:** `toneforge_midi_status` → `active_backend: winmm`, `ports_available: 1`,
`selected_port: ToneForge`, `ready: true`.

**Say:** "No Python MIDI package needed — it talks to the Windows MIDI driver
directly. And note what it refuses to claim."

---

## 1:08–1:24 — move the actual knob

**Type:**

> Set the amp gain to 80.

**Show:** `toneforge_set_parameter` →

```json
"value": 102, "bytes_hex": "B0 14 66", "applied": "unverified"
```

Cut to **AmpliTube**: the gain knob visibly moves to ~80%.

**Say:** "Eighty out of a hundred, converted to CC 102 on channel 1. The knob
moved — and ToneForge still labels the result 'unverified', because only
AmpliTube can prove it."

> If the room/recording cannot show AmpliTube (no loopMIDI installed), skip the
> cut and say: "The bytes are confirmed out of Windows; whether AmpliTube applied
> them needs the loopback port, which is a five-minute setup — documented, not
> faked." Show `bytes_hex` instead. **Never** stage a fake knob move.

---

## 1:24–1:30 — close

**Say:** "Seventeen tools, 149 tests, no third-party dependencies, no cloud. ToneForge designs
the tone, explains it, stores it, and moves the knobs you mapped — and it is
explicit about the difference."

**Show:** the tool list or the README header, then stop.

---

## Shot list (for the editor)

| # | Time | Content | Source |
|---|---|---|---|
| 1 | 0:00 | Empty chat + one-line framing | screen |
| 2 | 0:08 | Industrial-metal prompt → full recipe | `toneforge_create_preset` |
| 3 | 0:25 | Explanation bullets | same result, `why` |
| 4 | 0:38 | "Tighter + presence" → change list | `toneforge_adjust_preset` |
| 5 | 0:50 | Save → slug/version/path | `toneforge_save_preset` |
| 6 | 0:58 | Status → backend/port/ready | `toneforge_midi_status` |
| 7 | 1:08 | Gain 80 → `B0 14 66` → knob moves | `toneforge_set_parameter` + AmpliTube |
| 8 | 1:24 | Closing line | README / tool list |

## Narration (clean take, ~150 words)

> AmpliTube sounds great, but turning "I want a Rammstein-ish industrial tone" into
> actual knob positions is a skill. ToneForge does that part.
>
> One sentence in: genre, reference, tuning, three constraints. Out comes a full
> recipe — signal chain in order, amp and cab character, pedal settings, seven-band
> EQ, gate, and normalised gain, bass, mid, treble, presence, master. And it
> explains itself: the bass is trimmed because Drop D already supplies weight; the
> overdrive is a filter, not a distortion.
>
> "Tighter, more presence" gives a before-and-after list, field by field, and the
> stored preset stays untouched until I save it. Then it is a versioned JSON preset
> in the local library — not a fake AmpliTube file.
>
> The MIDI bridge needs no Python packages: it talks to the Windows MIDI driver
> directly. Gain to eighty becomes CC 102 — and the knob moves. ToneForge still
> calls the result unverified, because only AmpliTube can prove it. That honesty is
> the point.

## If something fails on camera

| Failure | Recovery |
|---|---|
| No MIDI port | Show `toneforge_midi_status` blockers; that is the honest state, and the checklist is on screen |
| Model ignores the tool | Re-prompt with the tool name: "use toneforge_create_preset" |
| Slow model turn | Cut the wait; keep the result |
| AmpliTube not responding | Check MIDI Input + channel on screen, then retry once — that is a useful 10 seconds, not a blooper |
