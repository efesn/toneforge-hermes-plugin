# Example prompts

What to say to Hermes, which tools fire, and what comes back. None of these
prompts require MIDI; the ones that do are marked **[MIDI]** and need the setup in
[`MIDI_SETUP_WINDOWS.md`](MIDI_SETUP_WINDOWS.md).

---

## Creating tones

**"Create a heavy industrial metal tone for Drop D, Rammstein-inspired, tight low end and controlled highs."**
→ `toneforge_create_preset(genre="industrial metal", reference="Rammstein", tuning="drop D", purpose="rhythm", instructions="tight low end, controlled highs")`
Back: 6-7 stage chain starting with a gate, gain 74, bass in the 30s, mids above neutral, HP around 90 Hz, plus the rationale.

**"Give me a Metallica-style rhythm tone in standard tuning."**
→ `toneforge_create_preset(genre="thrash", reference="Metallica", tuning="standard")`
Back: the thrash profile — mids pushed, lean bass, fast gate, no reverb wash.

**"Make a modern metalcore tone with a tight low end, Drop C."**
→ `toneforge_create_preset(genre="metalcore", tuning="drop C", instructions="tight low end")`
Back: overdrive *required* in front, presence slightly above treble, gate at ~-48 dB.

**"I want a 90s hard rock tone, Les Paul, half-step down."**
→ `toneforge_create_preset(genre="hard rock", pickup="humbucker", tuning="Eb standard")`
Back: gain 55, mid 62, gate off (a gate would clip note tails at this gain).

**"Something ambient and huge, clean amp, lots of space."**
→ `toneforge_create_preset(genre="ambient", instructions="more reverb, more delay")`
Back: gain ≤ 34, compressor optional, long delay + reverb as required stages.

**"Clean tone that stays clean when I dig in."**
→ `toneforge_create_preset(genre="clean")`
Back: gain 18, master 70, no gate, compressor suggestion.

**"Make my guitar sound heavier but keep the note definition."**
→ `toneforge_create_preset(instructions="heavier, keep note definition")`
Back: two modifiers fire — gain up **and** the definition trade (bass down, mid/presence up, HP up). The explanation says so explicitly.

**"Drop A, 7-string, maximum weight but no mud."**
→ `toneforge_create_preset(genre="modern metal", tuning="drop A", instructions="no mud")`
Back: bass pulled back hard, HP ~55 Hz, presence compensation.

---

## Adjusting

**"Make the low end tighter."**
→ `toneforge_adjust_preset(instructions="tighter")`
Back: `params.bass -5`, `eq.low_cut_hz +10`, `100 Hz -2 dB`, gate 3 dB tighter with a 20 ms faster decay — and a note that the stored preset was **not** modified.

**"Reduce the gain and increase the mids."**
→ `toneforge_adjust_preset(instructions="reduce the gain and increase the mids")`
Back: two independent modifiers, both in the change list.

**"Set the amp gain to 75."**
→ `toneforge_adjust_preset(instructions="set the amp gain to 75")`
(or `gain_level: 75`) Back: exactly 75 — explicit numbers are applied after adjectives.

**"Make it less muddy."**
→ `toneforge_adjust_preset(instructions="less muddy")`
Back: bass -4, 200 Hz -2 dB, 400 Hz +1 dB, HP +8 Hz, with the reason (200-300 Hz is the boxy region).

**"Add more presence and a bit of delay."**
→ `toneforge_adjust_preset(instructions="more presence, more delay")`
Back: presence +8, 3.2 kHz +2 dB, delay mix up, delay stage added to the chain.

**"Turn it into a lead tone."**
→ `toneforge_adjust_preset(instructions="make it a lead tone")`
Back: purpose switch — mid +6, gain +3, gate looser, delay/reverb mixes raised.

**"Bunu daha sıkı yap, gain'i azalt."** *(Turkish)*
→ `toneforge_adjust_preset(instructions="daha sıkı, gain azalt")`
Back: both the tight rule and the less-gain rule fire.

**"Save it as 'Sonne Rhythm'."**
→ `toneforge_adjust_preset(save_as="Sonne Rhythm")` or `toneforge_save_preset`
Back: slug `sonne-rhythm`, version 1, absolute path.

---

## Library

**"What tones do I have?"** → `toneforge_list_presets` → count + slugs, newest first.

**"Show me the Sonne preset."** → `toneforge_get_preset(preset="sonne")` → full config (partial names work if unambiguous).

**"Delete the test preset."** → `toneforge_delete_preset(preset="test", confirm=true)` — without `confirm` the tool refuses and asks.

**"What profiles does ToneForge have?"** → `toneforge_list_profiles(include_details=true)`

---

## MIDI

**"Is the MIDI bridge ready?"** **[MIDI]**
→ `toneforge_midi_status` → backend, port count, selection, mapping count, blockers, plus the 5-step AmpliTube checklist.

**"What MIDI ports can you see?"** **[MIDI]**
→ `toneforge_list_midi_ports` → ports with `looks_like_loopback` hints. Nothing is opened.

**"Use the ToneForge port."** **[MIDI]**
→ `toneforge_select_midi_port(port="ToneForge")` → persisted; survives restarts.

**"I assigned CC 20 to the gain knob in AmpliTube — remember that."** **[MIDI]**
→ `toneforge_map_parameter(parameter="amp_gain", cc=20, scope="preset")`

**"Set the amp gain to 80."** **[MIDI]**
→ `toneforge_set_parameter(parameter="amp_gain", value=80)` → `80/100 -> CC 102`, `B0 14 66`, `applied: "unverified"`.

**"Send CC 20 at 100."** **[MIDI]**
→ `toneforge_send_midi(cc=20, value=100)` → raw path for a mapping you have not stored.

**"Help me bind CC 22 — I'm in Learn mode."** **[MIDI]**
→ `toneforge_midi_probe(cc=22)` → sends `0 → 127 → 64`; AmpliTube binds at the first message and ends at ~50%.

**"Which parameters aren't mapped yet?"** **[MIDI]**
→ `toneforge_list_mappings` → count, per-mapping description, `unmapped_suggested`.

---

## What ToneForge will refuse to do (by design)

| Prompt | Response |
|---|---|
| "Write an AmpliTube `.at5p` file for this." | Refuses — the format is undocumented; stores a JSON recipe instead. |
| "Just send CC 7 to whatever port." | Refuses — no port selected, and CC 7 is not assumed to be anything. |
| "Load the preset into AmpliTube for me." | Explains the recipe must be dialled in by hand; it can only move already-assigned CCs. |
| "Delete all presets." | Requires `confirm=true` per call; there is no bulk delete. |
| "Make it sound exactly like the record." | States that references are tonal inspiration, not reproduction. |
