# 90-second demo script (v1.1)

Goal: natural language -> an explainable tone -> **a tone built from a real recording** ->
a stored preset. Record 1080p, one window (Hermes desktop), font one step up, no dead air.
Hard cap: 90 seconds.

**Before recording**

- `hermes plugins list | grep tone-forge` shows `enabled`; 17 tools registered.
- Fresh session, empty chat.
- One local reference file ready (any song you own) so the analysis is fast and offline.
- Optional, only if loopMIDI is running with a `ToneForge` port and a CC assigned in
  AmpliTube: keep AmpliTube open for Part E. **No loopback port? Skip Part E - never stage
  a knob move.**

---

## 0:00-0:07 - the problem

**Say:** "AmpliTube sounds great, but turning 'Rammstein-ish industrial, Drop D' into actual
knob positions is a skill. ToneForge does that part - and it can measure a real record
instead of guessing from a genre name."

**Show:** empty chat.

---

## 0:07-0:22 - create a tone

**Type:**

> Create a heavy industrial metal tone for Drop D, inspired by Rammstein's Sonne. Tight low end, controlled highs, keep note definition.

**Say:** "One tool call: genre, reference, tuning, three plain-language constraints."

**Show:** the result. Point at three things only:

- the **signal chain** - gate -> overdrive -> amp -> cab/mic -> post-EQ -> delay -> reverb
- the **parameters** - gain 74, bass 33, mid 65, presence 49
- the **explanation** - "bass is trimmed because Drop D already supplies weight"

---

## 0:22-0:52 - measure a real recording (the differentiator)

**Type:**

> Here's the track - build me the tone, the riff starts at 3:56.

**Paste:** the local file path (or a URL).

**Say:** "Same plugin, different evidence. It decodes the audio with ffmpeg, runs its own FFT,
and measures where the record's energy actually sits."

**Show, in this order:**

- `octave_bands_db` - "energy peaks at 63-125 Hz"
- `shape` - "95% rolloff at 3,359 Hz, slope -6.5 dB per octave: a dark, dense mix"
- `low_peaks` - "82.03 Hz, -7.9 cents off E2 -> standard E"
- `caveats` - **read one out loud:** "full mix, not an isolated guitar stem"

**Say:** "These numbers come from the audio, and it tells you what it can't know. That's the
difference between this and a prompt wrapper."

---

## 0:52-1:06 - adjust and save

**Type:**

> Reduce the gain by 5 and add presence. Save it as "Sonne Test".

**Say:** "The diff is a contract - field, before, after. The stored preset is untouched until
I say save."

**Show:** the `changes` list, then the saved slug + version.

---

## 1:06-1:22 - MIDI (only with a real loopback port)

**Type:**

> Set the amp gain to 80.

**Show:** `bytes_hex: "B0 14 66"`, then the knob moving in AmpliTube.

**Say:** "No `pip install` - it talks to Windows' MIDI driver directly, and only to CCs I
assigned myself. It reports `applied: unverified`, because only AmpliTube can confirm the
knob moved."

*No loopback port? Say instead:* "The bridge is real and tested against Windows' driver; the
last hop into AmpliTube needs a virtual cable I haven't installed, so I won't fake it." Then
go straight to the close.

---

## 1:22-1:30 - close

**Say:** "Seventeen tools, 151 tests, no third-party dependencies. It designs the tone,
explains it, stores it, measures a record when you have one - and it is explicit about what
it cannot verify."

**Show:** the preset library list, then stop.

---

## Shot list (for the editor)

| # | Time | Content | Source |
|---|---|---|---|
| 1 | 0:00 | Empty chat + framing | screen |
| 2 | 0:07 | Industrial-metal prompt -> recipe | `toneforge_create_preset` |
| 3 | 0:22 | Track prompt -> bands/shape/peaks | `toneforge_analyze_reference` |
| 4 | 0:38 | Caveats read aloud | same result, `caveats` |
| 5 | 0:52 | "Less gain, more presence" -> diff | `toneforge_adjust_preset` |
| 6 | 0:58 | Save -> slug/version | `toneforge_save_preset` |
| 7 | 1:06 | Gain 80 -> `B0 14 66` -> knob | `toneforge_set_parameter` + AmpliTube |
| 8 | 1:22 | Close | library list |

## Narration (clean take, ~150 words)

> AmpliTube sounds great, but turning "I want a Rammstein-ish industrial tone" into actual
> knob positions is a skill. ToneForge does that part.
>
> One sentence in: genre, reference, tuning, three constraints. Out comes a full recipe -
> signal chain in order, amp and cab character, pedals, seven-band EQ, gate, and normalised
> gain, bass, mid, treble, presence, master. And it explains itself: the bass is trimmed
> because Drop D already supplies weight; the overdrive is a filter, not a distortion.
>
> Then the part a prompt can't do: give it the actual recording and it measures it - band
> balance, spectral slope, where the mix rolls off, the low-frequency peaks that identify the
> tuning. It says "full mix, not an isolated guitar stem" out loud, because that is the limit
> of what a mix can tell you.
>
> "Less gain, more presence" gives a before-and-after list, field by field, and the preset
> stays untouched until I save it. Then it is a versioned JSON preset - not a fake AmpliTube
> file.

## If something fails on camera

| Failure | Recovery |
|---|---|
| No MIDI port | Show `toneforge_midi_status` blockers; that is the honest state |
| Analysis says "tuning not determined" | Say the clip is too short, then pass `tuning` explicitly in a second call |
| Model ignores the tool | Re-prompt naming the tool: "use toneforge_analyze_reference" |
| Slow model turn | Cut the wait, keep the result |
| ffmpeg missing | `ffmpeg -version` on screen, then install - or skip to Part D and say why |
