"""Tone profile library: tunings, pickups, purposes and the nine stock profiles.

Design rules baked into this data
---------------------------------
* Parameters are **normalised 0-100**, i.e. ToneForge's own scale, not a claim
  about how AmpliTube displays a knob. The mapping to AmpliTube's UI range is
  done by the player, once, by ear.
* EQ values are **dB targets** for a 7-band graphic EQ (100 Hz ... 6.4 kHz).
  They are equally usable as "boost/cut this region" instructions for an amp's
  tone stack.
* No profile names an AmpliTube model. Profiles describe *amp families and
  characters* plus browser search terms, because model availability differs
  between AmpliTube 5 editions and ToneForge cannot verify what is installed.
* Gain values are starting points, chosen so that a humbucker-equipped guitar
  lands in the intended zone. The engine shifts them for pickup and tuning.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Tunings
# --------------------------------------------------------------------------- #
# bass_trim      : subtracted from the amp bass control (lower tunings need less
#                  low end, not more)
# low_cut_hz     : high-pass target for the post-amp EQ
# gate_trim_db   : how much tighter the gate should be than the profile default
# presence_trim  : small presence compensation for the darker fundamental
TUNINGS: dict[str, dict[str, Any]] = {
    "standard": {
        "label": "Standard E (E A D G B e)",
        "low_string": "E2",
        "semitones_down": 0,
        "bass_trim": 0,
        "low_cut_hz": 82,
        "gate_trim_db": 0,
        "presence_trim": 0,
        "note": "Reference tuning; no compensation applied.",
    },
    "eb_standard": {
        "label": "Eb standard (Eb Ab Db Gb Bb eb)",
        "low_string": "Eb2",
        "semitones_down": 1,
        "bass_trim": 2,
        "low_cut_hz": 78,
        "gate_trim_db": 1,
        "presence_trim": 1,
        "note": "Slightly darker and looser than E; trim a little bass and add a touch of presence.",
    },
    "d_standard": {
        "label": "D standard (D G C F A d)",
        "low_string": "D2",
        "semitones_down": 2,
        "bass_trim": 3,
        "low_cut_hz": 74,
        "gate_trim_db": 1,
        "presence_trim": 1,
        "note": "Full-step-down; keep the low end controlled or chords turn to mud.",
    },
    "drop_d": {
        "label": "Drop D (D A D G B e)",
        "low_string": "D2",
        "semitones_down": 2,
        "bass_trim": 4,
        "low_cut_hz": 76,
        "gate_trim_db": 2,
        "presence_trim": 0,
        "note": "Power chords on the low three strings are the point: clarity there matters more than depth.",
    },
    "drop_c": {
        "label": "Drop C (C G C F A d)",
        "low_string": "C2",
        "semitones_down": 4,
        "bass_trim": 6,
        "low_cut_hz": 68,
        "gate_trim_db": 3,
        "presence_trim": 2,
        "note": "Needs a tight gate and a firm low cut; the amp's bass control stops helping below this point.",
    },
    "c_standard": {
        "label": "C standard (C F Bb Eb G c)",
        "low_string": "C2",
        "semitones_down": 4,
        "bass_trim": 7,
        "low_cut_hz": 64,
        "gate_trim_db": 3,
        "presence_trim": 2,
        "note": "Low and thick; pull bass back and lean on the midrange for definition.",
    },
    "drop_b": {
        "label": "Drop B (B F# B E G# c#)",
        "low_string": "B1",
        "semitones_down": 5,
        "bass_trim": 8,
        "low_cut_hz": 60,
        "gate_trim_db": 4,
        "presence_trim": 3,
        "note": "Baritone territory: an overdrive in front does more for tightness than any EQ move.",
    },
    "b_standard": {
        "label": "B standard / 7-string (B E A D G B e)",
        "low_string": "B1",
        "semitones_down": 5,
        "bass_trim": 8,
        "low_cut_hz": 58,
        "gate_trim_db": 4,
        "presence_trim": 3,
        "note": "Seven-string low B behaves like a bass note; treat the first two strings separately in the mix.",
    },
    "drop_a": {
        "label": "Drop A (A E A D F# b)",
        "low_string": "A1",
        "semitones_down": 7,
        "bass_trim": 10,
        "low_cut_hz": 54,
        "gate_trim_db": 5,
        "presence_trim": 4,
        "note": "Extreme low end: high-pass aggressively and let the bass guitar own 60-100 Hz.",
    },
}

TUNING_ALIASES: dict[str, str] = {
    "standard": "standard", "e standard": "standard", "e": "standard", "440": "standard",
    "standard e": "standard", "estandard": "standard", "normal": "standard",
    "eb": "eb_standard", "eb standard": "eb_standard", "e flat": "eb_standard",
    "half step down": "eb_standard", "half-step down": "eb_standard", "eb_standard": "eb_standard",
    "d standard": "d_standard", "d_standard": "d_standard", "full step down": "d_standard",
    "drop d": "drop_d", "drop_d": "drop_d", "dropd": "drop_d", "d drop": "drop_d",
    "drop c": "drop_c", "drop_c": "drop_c", "dropc": "drop_c",
    "c standard": "c_standard", "c_standard": "c_standard",
    "drop b": "drop_b", "drop_b": "drop_b",
    "b standard": "b_standard", "b_standard": "b_standard", "7 string": "b_standard",
    "7-string": "b_standard", "seven string": "b_standard", "baritone": "b_standard",
    "drop a": "drop_a", "drop_a": "drop_a",
    # Turkish
    "standart": "standard", "drop re": "drop_d", "re akort": "drop_d",
    "mi bemol": "eb_standard", "yarim ses asagi": "eb_standard",
}

# --------------------------------------------------------------------------- #
# Pickups
# --------------------------------------------------------------------------- #
PICKUPS: dict[str, dict[str, Any]] = {
    "humbucker": {
        "label": "Humbucker (passive)",
        "gain_bias": 0,
        "treble_bias": 0,
        "bass_bias": 0,
        "noise": "low",
        "note": "The reference pickup: full output, strong low mids, hum-cancelling.",
    },
    "active_humbucker": {
        "label": "Active humbucker",
        "gain_bias": -4,
        "treble_bias": 3,
        "bass_bias": -2,
        "noise": "very low",
        "note": "Hotter and more linear than passive; back the gain off and expect a firmer top end.",
    },
    "single_coil": {
        "label": "Single coil",
        "gain_bias": 6,
        "treble_bias": -3,
        "bass_bias": 3,
        "noise": "high",
        "note": "Brighter and noisier: more gain to reach the same saturation, and a tighter gate.",
    },
    "p90": {
        "label": "P-90",
        "gain_bias": 2,
        "treble_bias": -1,
        "bass_bias": 2,
        "noise": "medium",
        "note": "Mid-forward and gritty; excellent for classic and industrial rock, less obedient under high gain.",
    },
    "mini_humbucker": {
        "label": "Mini humbucker",
        "gain_bias": 2,
        "treble_bias": -2,
        "bass_bias": 1,
        "noise": "low",
        "note": "Tighter and brighter than a full humbucker; keeps chord definition under gain.",
    },
    "piezo": {
        "label": "Piezo / acoustic",
        "gain_bias": 10,
        "treble_bias": -6,
        "bass_bias": 4,
        "noise": "very low",
        "note": "Piezo output is bright and percussive; high gain exposes pick attack as harshness.",
    },
}

PICKUP_ALIASES: dict[str, str] = {
    "humbucker": "humbucker", "hb": "humbucker", "hum": "humbucker", "passive": "humbucker",
    "double coil": "humbucker", "cift bobin": "humbucker",
    "active": "active_humbucker", "active humbucker": "active_humbucker", "emg": "active_humbucker",
    "single coil": "single_coil", "single": "single_coil", "strat": "single_coil",
    "sc": "single_coil", "tek bobin": "single_coil",
    "p90": "p90", "p-90": "p90", "soapbar": "p90",
    "mini humbucker": "mini_humbucker", "mini": "mini_humbucker", "firebird": "mini_humbucker",
    "piezo": "piezo", "acoustic": "piezo", "akustik": "piezo",
}

# --------------------------------------------------------------------------- #
# Purposes
# --------------------------------------------------------------------------- #
# Deltas are applied on top of the profile so that "lead version of the
# industrial profile" stays recognisably industrial.
PURPOSES: dict[str, dict[str, Any]] = {
    "rhythm": {
        "label": "Rhythm",
        "params": {"bass": -2, "mid": 2, "presence": 0, "gain": 0},
        "gate": {"enabled": True, "threshold_db": -2, "decay_ms": -20},
        "space": {"delay_mix": 0.05, "reverb_mix": 0.10},
        "note": "Tight, dry and consistent: rhythm parts are judged on how they sit under a vocal.",
    },
    "lead": {
        "label": "Lead",
        "params": {"mid": 6, "treble": 2, "gain": 3, "bass": -1},
        "gate": {"enabled": True, "threshold_db": 4, "decay_ms": 60},
        "space": {"delay_mix": 0.22, "reverb_mix": 0.18},
        "note": "Mids forward and slightly more gain so single notes sing above the band.",
    },
    "solo": {
        "label": "Solo",
        "params": {"mid": 7, "presence": 3, "gain": 3},
        "gate": {"enabled": True, "threshold_db": 6, "decay_ms": 80},
        "space": {"delay_mix": 0.26, "reverb_mix": 0.22},
        "note": "Like Lead, with more sustain and space: the gate is loosened so held notes bloom.",
    },
    # Clean/ambient/crunch cap the gain instead of subtracting a fixed amount:
    # a -40 delta cleans up a high-gain profile but starves a clean one.
    "clean": {
        "label": "Clean",
        "params": {"bass": 1, "mid": 0, "treble": 2, "presence": 1},
        "gain_cap": 30,
        "gate": {"enabled": False},
        "space": {"delay_mix": 0.08, "reverb_mix": 0.22},
        "note": "Headroom first: gain is capped so the amp stays clean when you dig in.",
    },
    "ambient": {
        "label": "Ambient",
        "params": {"treble": 3, "presence": 4},
        "gain_cap": 34,
        "gate": {"enabled": False},
        "space": {"delay_mix": 0.35, "reverb_mix": 0.45},
        "note": "Effects carry the part; the amp stays articulate so the reverb tail keeps shape.",
    },
    "crunch": {
        "label": "Crunch",
        "params": {"gain": -12, "mid": 3, "treble": 1},
        "gain_cap": 55,
        "gate": {"enabled": False},
        "space": {"delay_mix": 0.05, "reverb_mix": 0.14},
        "note": "Edge-of-breakup: volume knob and pick attack do the tonal work.",
    },
}

PURPOSE_ALIASES: dict[str, str] = {
    "rhythm": "rhythm", "rythm": "rhythm", "riff": "rhythm", "ritim": "rhythm", "ritm": "rhythm",
    "lead": "lead", "solo": "solo", "melody": "lead", "melodi": "lead",
    "clean": "clean", "temiz": "clean", "crunch": "crunch", "kirli": "crunch",
    "ambient": "ambient", "atmospheric": "ambient", "atmosferik": "ambient",
}

# --------------------------------------------------------------------------- #
# Stock profiles
# --------------------------------------------------------------------------- #
# Signal chain is assembled from these blocks by the engine; the order is fixed
# by `CHAIN_ORDER` so a preset always renders the same way.
PROFILES: dict[str, dict[str, Any]] = {
    "industrial_metal": {
        "label": "Industrial Metal",
        "aliases": [
            "industrial", "industrial metal", "endustriyel metal", "ndh",
            "neue deutsche harte", "tanzmetall", "rammstein", "sonne",
            "rammstein-inspired", "gothic metal", "industrial rock",
        ],
        "default_tuning": "drop_d",
        "default_purpose": "rhythm",
        "amp": {
            "category": "Modern high-gain channel with a tight, dry power section",
            "family": "Hot-rodded British high gain",
            "character": "Percussive and mid-forward; the distortion stays articulate instead of turning to fizz",
            "search_terms": ["high gain", "british", "hot rodded", "modern", "lead channel"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12",
            "speaker_character": "Vintage-30 family: strong low-mid punch, controlled top",
            "note": "The closed cab keeps the low end fast; avoid oversized cabs for this style.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis, just inside the dust cap edge, ~2 cm from the grille",
            "note": "Move 2-3 cm toward the cone edge to soften the 2-4 kHz bite.",
        },
        "params": {"gain": 74, "bass": 46, "mid": 58, "treble": 52, "presence": 46, "master": 55},
        "eq": {
            "low_cut_hz": 78,
            "high_cut_hz": 11000,
            "bands": [
                {"hz": 100, "db": -2}, {"hz": 200, "db": -1}, {"hz": 400, "db": 1},
                {"hz": 800, "db": 2}, {"hz": 1600, "db": 1}, {"hz": 3200, "db": -1},
                {"hz": 6400, "db": -2},
            ],
        },
        "gate": {"enabled": True, "threshold_db": -44, "decay_ms": 90, "hold_ms": 20},
        "pedals": [
            {
                "slot": "pre", "type": "Noise gate", "required": True,
                "settings": {"threshold_db": -44, "decay_ms": 90, "hold_ms": 20},
                "purpose": "Kills the idle hiss of a high-gain channel between chugs.",
            },
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": False,
                "settings": {"drive": 12, "level": 55, "tone": 45},
                "purpose": "Tightens the low end and adds upper-mid attack before the amp sees the signal.",
            },
        ],
        "post": [
            "Double-track the same part and hard-pan the two takes; this is what makes the riff sound wide.",
            "Roll off everything below ~70 Hz on the guitar bus so the bass and kick keep that region.",
            "A short plate or room reverb (0.6-1.0 s) at low mix adds the 'room' without washing out the gate.",
            "Keep the guitar bus dry-ish: industrial metal lives on precision, not on ambience.",
        ],
        "why": [
            "The low end is trimmed (bass 46, 100 Hz at -2 dB) because Drop D already supplies weight; extra bass only blurs the palm mutes.",
            "Mids sit above neutral (58, +2 dB at 800 Hz) so the riff cuts through a dense synth and drum production.",
            "Presence is deliberately below treble (46 vs 52): the top end should be controlled, not brittle.",
            "The overdrive is used as a filter, not a distortion: low drive, high level, which tightens the low end.",
            "A hard gate plus a fast decay keeps the space between chugs silent, which is half of the genre's sound.",
        ],
    },
    "modern_metal": {
        "label": "Modern Metal",
        "aliases": [
            "modern metal", "modern", "metal", "progressive metal", "prog metal",
            "metalcore-adjacent", "djent", "modern high gain", "modern metal rhythm",
        ],
        "default_tuning": "drop_c",
        "default_purpose": "rhythm",
        "amp": {
            "category": "High-gain channel with a fast, scooped-mid response",
            "family": "American modern high gain",
            "character": "Big and compressed, with a wide low end that needs taming rather than feeding",
            "search_terms": ["high gain", "american", "modern", "rhythm channel"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12",
            "speaker_character": "Modern heavy-duty speaker with a tight low resonance",
            "note": "Avoid dark, mid-heavy cabs here; the amp already supplies the weight.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis at the cap edge, 3-5 cm back",
            "note": "A little distance smooths the fizz that modern high gain produces.",
        },
        "params": {"gain": 78, "bass": 52, "mid": 44, "treble": 58, "presence": 54, "master": 52},
        "eq": {
            "low_cut_hz": 72,
            "high_cut_hz": 10500,
            "bands": [
                {"hz": 100, "db": 1}, {"hz": 200, "db": -1}, {"hz": 400, "db": -2},
                {"hz": 800, "db": 1}, {"hz": 1600, "db": 2}, {"hz": 3200, "db": 0},
                {"hz": 6400, "db": -1},
            ],
        },
        "gate": {"enabled": True, "threshold_db": -42, "decay_ms": 110, "hold_ms": 25},
        "pedals": [
            {
                "slot": "pre", "type": "Noise gate", "required": True,
                "settings": {"threshold_db": -42, "decay_ms": 110, "hold_ms": 25},
                "purpose": "Modern high gain is noisy by nature; the gate is part of the sound.",
            },
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": False,
                "settings": {"drive": 8, "level": 60, "tone": 50},
                "purpose": "Low-drive boost to restore pick definition in the scooped midrange.",
            },
        ],
        "post": [
            "High-pass at 70-80 Hz and let the bass guitar own the sub region.",
            "Consider a multiband compressor on the low mids if the palm mutes jump out.",
            "Double-track wide; a single take of modern high gain always sounds smaller than it feels.",
        ],
        "why": [
            "Gain is high (78) but not maxed: past roughly 80 the amp compresses into mush and loses transient detail.",
            "Mids are scooped (44) for the wide modern voicing, then partly restored at 1.6 kHz so single notes still speak.",
            "Bass at 52 with a 100 Hz shelf boost gives the 'big' impression while the 72 Hz high-pass keeps it fast.",
            "The gate threshold is slightly lower than the industrial profile because the amp itself is noisier.",
        ],
    },
    "thrash_metal": {
        "label": "Thrash Metal",
        "aliases": [
            "thrash", "thrash metal", "speed metal", "bay area", "slayer", "megadeth",
            "metallica", "testament", "exodus", "80s thrash",
        ],
        "default_tuning": "standard",
        "default_purpose": "rhythm",
        "amp": {
            "category": "Tight high-gain channel with an aggressive, dry midrange",
            "family": "Hot-rodded British high gain (modded Marshall lineage)",
            "character": "Percussive attack, lean low end, midrange that bites rather than smooths",
            "search_terms": ["high gain", "british", "thrash", "rhythm"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12",
            "speaker_character": "Greenback/V30-family: fast and mid-forward",
            "note": "A mid-forward cab is what makes downpicked riffs read at speed.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis, cap edge, very close",
            "note": "Close miking keeps the transient sharp, which is the whole point at these tempos.",
        },
        "params": {"gain": 70, "bass": 48, "mid": 62, "treble": 60, "presence": 52, "master": 55},
        "eq": {
            "low_cut_hz": 85,
            "high_cut_hz": 12000,
            "bands": [
                {"hz": 100, "db": -3}, {"hz": 200, "db": -1}, {"hz": 400, "db": 2},
                {"hz": 800, "db": 3}, {"hz": 1600, "db": 1}, {"hz": 3200, "db": 0},
                {"hz": 6400, "db": -1},
            ],
        },
        "gate": {"enabled": True, "threshold_db": -46, "decay_ms": 70, "hold_ms": 15},
        "pedals": [
            {
                "slot": "pre", "type": "Noise gate", "required": True,
                "settings": {"threshold_db": -46, "decay_ms": 70, "hold_ms": 15},
                "purpose": "Fast decay for staccato downpicking; the riff needs silence between notes.",
            },
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": False,
                "settings": {"drive": 15, "level": 50, "tone": 55},
                "purpose": "Optional: tightens the low end if the amp gets flubby at volume.",
            },
        ],
        "post": [
            "Keep it dry: short room, low mix, no long tails.",
            "High-pass around 85 Hz; thrash guitars are midrange instruments in the mix.",
        ],
        "why": [
            "Mids are pushed (62, +3 dB at 800 Hz) so fast alternate picking stays legible instead of blurring.",
            "Bass is kept lean (48) and high-passed at 85 Hz: low end slows down the perceived attack.",
            "Gain stays at 70 - more than this smears the pick attack that defines the genre.",
            "The gate decays fast (70 ms) to match staccato riffing.",
        ],
    },
    "metalcore": {
        "label": "Metalcore",
        "aliases": [
            "metalcore", "core", "post-hardcore", "melodic metalcore", "kse",
            "killswitch", "august burns red", "modern core",
        ],
        "default_tuning": "drop_c",
        "default_purpose": "rhythm",
        "amp": {
            "category": "Modern high-gain channel with a controlled, tight response",
            "family": "American/British hybrid high gain",
            "character": "Fast and compressed, with enough midrange for melodic leads to sit on top",
            "search_terms": ["high gain", "modern", "rhythm", "lead"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12",
            "speaker_character": "V30-family",
            "note": "Predictable and dense; works for both the rhythm wall and the lead tone.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis, between cap and edge, 2-3 cm back",
            "note": "Slightly off the cap keeps the 3 kHz region from getting harsh under gain.",
        },
        "params": {"gain": 73, "bass": 50, "mid": 55, "treble": 60, "presence": 57, "master": 53},
        "eq": {
            "low_cut_hz": 76,
            "high_cut_hz": 11500,
            "bands": [
                {"hz": 100, "db": -1}, {"hz": 200, "db": -1}, {"hz": 400, "db": 1},
                {"hz": 800, "db": 2}, {"hz": 1600, "db": 2}, {"hz": 3200, "db": 1},
                {"hz": 6400, "db": -1},
            ],
        },
        "gate": {"enabled": True, "threshold_db": -43, "decay_ms": 100, "hold_ms": 20},
        "pedals": [
            {
                "slot": "pre", "type": "Noise gate", "required": True,
                "settings": {"threshold_db": -43, "decay_ms": 100, "hold_ms": 20},
                "purpose": "Tight enough for staccato riffs, loose enough to let harmonics ring.",
            },
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": True,
                "settings": {"drive": 18, "level": 58, "tone": 52},
                "purpose": "The defining pedal: mid push plus low-end tightening before the amp.",
            },
        ],
        "post": [
            "High-pass 75-80 Hz, then a gentle dip at 300-400 Hz to clear space for the kick.",
            "Parallel compression on the guitar bus glues the clean and distorted sections together.",
        ],
        "why": [
            "Overdrive is mandatory here: it is what separates a modern core tone from a plain high-gain channel.",
            "Presence (57) sits above treble (60) only slightly - enough for pick attack without hiss.",
            "Mids at 55 with +2 dB at 800 Hz and 1.6 kHz keeps both chugs and melodic leads working.",
        ],
    },
    "hard_rock": {
        "label": "Hard Rock",
        "aliases": [
            "hard rock", "rock", "classic hard rock", "80s rock", "hair metal",
            "guns n roses", "acdc", "ac/dc", "led zeppelin", "aerosmith", "sert rock",
        ],
        "default_tuning": "eb_standard",
        "default_purpose": "crunch",
        "amp": {
            "category": "Medium-high gain crunch channel",
            "family": "British rock (plexi / JCM lineage)",
            "character": "Open and dynamic, with a midrange bark and a top end that stays musical",
            "search_terms": ["british", "crunch", "rock", "plexi"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12",
            "speaker_character": "Greenback-family: warm low mids, soft top",
            "note": "Greenbacks break up pleasantly; they are part of the sound, not a neutral monitor.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis, cap edge, 3-5 cm back",
            "note": "A little distance lets the cab breathe instead of sounding like a laser.",
        },
        "params": {"gain": 55, "bass": 55, "mid": 62, "treble": 57, "presence": 48, "master": 62},
        "eq": {
            "low_cut_hz": 88,
            "high_cut_hz": 12000,
            "bands": [
                {"hz": 100, "db": 0}, {"hz": 200, "db": 1}, {"hz": 400, "db": 2},
                {"hz": 800, "db": 2}, {"hz": 1600, "db": 1}, {"hz": 3200, "db": 0},
                {"hz": 6400, "db": -1},
            ],
        },
        "gate": {"enabled": False, "threshold_db": -55, "decay_ms": 200, "hold_ms": 40},
        "pedals": [
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": False,
                "settings": {"drive": 20, "level": 50, "tone": 55},
                "purpose": "Optional solo boost, not a distortion: the amp supplies the gain.",
            },
            {
                "slot": "post_amp", "type": "Graphic EQ", "required": False,
                "settings": {"preset": "mid bump", "mid_boost_db": 3},
                "purpose": "Lifts the solo without changing the rhythm sound.",
            },
        ],
        "post": [
            "Short room reverb (0.8 s) at low mix for the 'big room' impression.",
            "A touch of tape saturation on the bus helps the guitars sit with drums.",
        ],
        "why": [
            "Gain is moderate (55): hard rock lives on power-amp compression, not preamp saturation.",
            "Mids are strong (62) because the genre's guitar sound is fundamentally a midrange instrument.",
            "The gate is off by default: at this gain level it would clip note tails and kill the dynamics.",
        ],
    },
    "classic_rock": {
        "label": "Classic Rock",
        "aliases": [
            "classic rock", "60s rock", "70s rock", "blues rock", "vintage rock",
            "led zeppelin", "hendrix", "cream", "klasik rock", "blues",
        ],
        "default_tuning": "standard",
        "default_purpose": "crunch",
        "amp": {
            "category": "Low-to-medium gain vintage channel",
            "family": "Non-master-volume British / American vintage",
            "character": "Open, uncompressed and touch-sensitive; cleans up with the guitar volume",
            "search_terms": ["vintage", "british", "clean", "crunch", "american"],
        },
        "cabinet": {
            "configuration": "Open-back 2x12 or 4x10",
            "speaker_character": "Alnico or greenback family, warm and slightly loose",
            "note": "Open-backed cabs give the airy spread this music was recorded with.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "Off-axis, 8-12 cm back",
            "note": "Off-axis placement softens the top end the way vintage recordings sound.",
        },
        "params": {"gain": 42, "bass": 48, "mid": 66, "treble": 54, "presence": 44, "master": 68},
        "eq": {
            "low_cut_hz": 90,
            "high_cut_hz": 10500,
            "bands": [
                {"hz": 100, "db": 0}, {"hz": 200, "db": 1}, {"hz": 400, "db": 1},
                {"hz": 800, "db": 2}, {"hz": 1600, "db": 1}, {"hz": 3200, "db": -1},
                {"hz": 6400, "db": -2},
            ],
        },
        "gate": {"enabled": False, "threshold_db": -60, "decay_ms": 300, "hold_ms": 60},
        "pedals": [
            {
                "slot": "pre", "type": "Fuzz or germanium overdrive", "required": False,
                "settings": {"drive": 35, "level": 45, "tone": 50},
                "purpose": "For the heavier end of the era; leave it off for cleaner passages.",
            },
        ],
        "post": [
            "Plate reverb (1.2-1.6 s) at low-to-medium mix, the classic studio signature.",
            "Do not high-pass aggressively; the loose low end is part of the charm.",
        ],
        "why": [
            "Gain is low (42) and the master is high (68): the power section, not the preamp, provides the compression.",
            "Mids are the highest of any profile (66) - this era's guitar sound is essentially all midrange.",
            "The top end is rolled back (treble 54, -2 dB at 6.4 kHz) to match the darker recordings of the period.",
        ],
    },
    "clean": {
        "label": "Clean",
        "aliases": [
            "clean", "clean tone", "temiz", "sparkle", "fender clean", "jazz clean",
            "pedal platform", "country clean",
        ],
        "default_tuning": "standard",
        "default_purpose": "clean",
        "amp": {
            "category": "High-headroom clean channel",
            "family": "American 6L6/6V6 clean",
            "character": "Round lows, scooped mids and a bell-like top end that stays clean when pushed",
            "search_terms": ["clean", "american", "vintage", "high headroom"],
        },
        "cabinet": {
            "configuration": "Open-back 1x12 or 2x12",
            "speaker_character": "American-voiced speaker with a wide, open top end",
            "note": "Open back plus an American speaker is the classic clean platform.",
        },
        "mic": {
            "type": "Condenser or dynamic",
            "family": "Large-diaphragm condenser or SM57-style",
            "position": "On-axis, slightly off the dust cap, 10-15 cm back",
            "note": "Condensers capture the sparkle; back the distance off to avoid harshness.",
        },
        "params": {"gain": 18, "bass": 50, "mid": 52, "treble": 56, "presence": 50, "master": 70},
        "eq": {
            "low_cut_hz": 70,
            "high_cut_hz": 14000,
            "bands": [
                {"hz": 100, "db": 0}, {"hz": 200, "db": -1}, {"hz": 400, "db": -1},
                {"hz": 800, "db": 0}, {"hz": 1600, "db": 1}, {"hz": 3200, "db": 1},
                {"hz": 6400, "db": 0},
            ],
        },
        "gate": {"enabled": False, "threshold_db": -70, "decay_ms": 400, "hold_ms": 80},
        "pedals": [
            {
                "slot": "pre", "type": "Compressor", "required": False,
                "settings": {"threshold_db": -24, "ratio": 3.0, "attack_ms": 15, "release_ms": 180},
                "purpose": "Evens out fingerpicking and adds sustain without adding dirt.",
            },
            {
                "slot": "post_amp", "type": "Chorus / modulation", "required": False,
                "settings": {"rate_hz": 0.6, "depth": 30, "mix": 20},
                "purpose": "Adds width for arpeggios; keep the mix low so it stays a clean tone.",
            },
        ],
        "post": [
            "Compress lightly on the bus (2:1, slow attack) to keep transients intact.",
            "Use a short room reverb rather than a plate; cleans get muddy under long tails.",
        ],
        "why": [
            "Gain is near minimum (18) so the amp stays clean at stage volume; headroom is the whole design goal.",
            "Master is high (70) to get volume from the power section without pushing the preamp.",
            "No gate: a clean tone's note tails and finger noise are musical information, not noise.",
        ],
    },
    "ambient": {
        "label": "Ambient",
        "aliases": [
            "ambient", "atmospheric", "post rock", "shoegaze", "texture", "atmosferik",
            "soundscape", "pad", "cinematic",
        ],
        "default_tuning": "standard",
        "default_purpose": "ambient",
        "amp": {
            "category": "Clean-to-edge-of-breakup channel",
            "family": "American clean or Vox-style chime",
            "character": "Articulate but soft, with a top end that stays smooth under long delays",
            "search_terms": ["clean", "chime", "vintage", "american"],
        },
        "cabinet": {
            "configuration": "Open-back 2x12",
            "speaker_character": "Warm, slightly dark speaker",
            "note": "A dark cab keeps stacked delays from turning brittle.",
        },
        "mic": {
            "type": "Ribbon or condenser",
            "family": "Ribbon or large-diaphragm condenser",
            "position": "Off-axis, 15-25 cm back",
            "note": "Distance and off-axis placement give the reverb something natural to sit in.",
        },
        "params": {"gain": 26, "bass": 50, "mid": 50, "treble": 58, "presence": 54, "master": 64},
        "eq": {
            "low_cut_hz": 65,
            "high_cut_hz": 12500,
            "bands": [
                {"hz": 100, "db": 0}, {"hz": 200, "db": 0}, {"hz": 400, "db": -1},
                {"hz": 800, "db": 0}, {"hz": 1600, "db": 0}, {"hz": 3200, "db": 1},
                {"hz": 6400, "db": 0},
            ],
        },
        "gate": {"enabled": False, "threshold_db": -70, "decay_ms": 500, "hold_ms": 100},
        "pedals": [
            {
                "slot": "pre", "type": "Compressor", "required": False,
                "settings": {"threshold_db": -26, "ratio": 2.5, "attack_ms": 25, "release_ms": 250},
                "purpose": "Keeps the long tails even as the part gets quieter.",
            },
            {
                "slot": "post_amp", "type": "Delay (analog/tape)", "required": True,
                "settings": {"time_ms": 420, "feedback": 0.38, "mix": 0.30},
                "purpose": "The rhythmic pulse under the pad; tape-style repeats blur into the reverb.",
            },
            {
                "slot": "post_amp", "type": "Reverb (large hall/plate)", "required": True,
                "settings": {"decay_s": 4.5, "pre_delay_ms": 40, "mix": 0.45},
                "purpose": "The space itself. Pre-delay keeps the pick attack readable inside the wash.",
            },
        ],
        "post": [
            "Do not high-pass above 90 Hz; the low end of a reverb tail is part of the texture.",
            "Sidechain the reverb against the dry signal if the part needs to stay intelligible.",
        ],
        "why": [
            "Gain stays low (26) because saturation fights the effects; the amp is a clean voice, not a distortion source.",
            "Treble and presence are raised slightly (58/54) so the dry signal survives the reverb wash.",
            "No gate at all: cutting the tail would remove the reverb.",
        ],
    },
    "lead": {
        "label": "Lead / Solo",
        "aliases": [
            "lead", "solo", "lead tone", "melodic lead", "shred", "solo tone", "lead guitar",
        ],
        "default_tuning": "standard",
        "default_purpose": "lead",
        "amp": {
            "category": "High-gain lead channel with a mid-forward voicing",
            "family": "Hot-rodded British or American lead channel",
            "character": "Singing sustain with strong upper mids; compresses smoothly when you dig in",
            "search_terms": ["lead", "high gain", "solo", "modern"],
        },
        "cabinet": {
            "configuration": "Closed-back 4x12 or 2x12",
            "speaker_character": "V30-family: mid punch that helps single notes cut",
            "note": "A mid-forward cab does most of the work of making a lead sit in a mix.",
        },
        "mic": {
            "type": "Dynamic",
            "family": "SM57-style",
            "position": "On-axis, cap edge, 3 cm back",
            "note": "Move slightly off-axis for a rounder, less aggressive lead.",
        },
        "params": {"gain": 70, "bass": 50, "mid": 66, "treble": 58, "presence": 56, "master": 58},
        "eq": {
            "low_cut_hz": 90,
            "high_cut_hz": 11500,
            "bands": [
                {"hz": 100, "db": -1}, {"hz": 200, "db": 0}, {"hz": 400, "db": 2},
                {"hz": 800, "db": 3}, {"hz": 1600, "db": 2}, {"hz": 3200, "db": 0},
                {"hz": 6400, "db": -1},
            ],
        },
        "gate": {"enabled": True, "threshold_db": -50, "decay_ms": 180, "hold_ms": 40},
        "pedals": [
            {
                "slot": "pre", "type": "Overdrive / clean boost", "required": True,
                "settings": {"drive": 14, "level": 62, "tone": 52},
                "purpose": "Adds mids and compression so legato passages stay even.",
            },
            {
                "slot": "post_amp", "type": "Delay", "required": True,
                "settings": {"time_ms": 340, "feedback": 0.22, "mix": 0.20},
                "purpose": "Adds depth without smearing fast lines; keep the mix under ~25%.",
            },
        ],
        "post": [
            "Slightly narrower stereo image than the rhythm guitars, so the lead sits in the centre.",
            "Automate a small mid boost for the solo section if the arrangement is dense.",
        ],
        "why": [
            "Mids are the highest of the metal profiles (66) and the master is moderate (58): the lead needs to be heard, not loud.",
            "The gate is looser than the rhythm gate (180 ms decay) so long notes and vibrato are not cut off.",
            "Delay is part of the sound, not an afterthought: a short slap at low mix gives the line depth.",
        ],
    },
}

# Deterministic signal-chain skeleton. `optional` stages are only rendered when
# a pedal of that family is present.
CHAIN_ORDER: list[dict[str, Any]] = [
    {"key": "noise_gate", "slot": "pre", "role": "Noise gate", "optional": True},
    {"key": "boost", "slot": "pre", "role": "Overdrive / boost", "optional": True},
    {"key": "compressor", "slot": "pre", "role": "Compressor", "optional": True},
    {"key": "amp", "slot": "amp", "role": "Amplifier", "optional": False},
    {"key": "cabinet", "slot": "cab", "role": "Cabinet + microphone", "optional": False},
    {"key": "post_eq", "slot": "post_amp", "role": "Post-amp EQ", "optional": False},
    {"key": "modulation", "slot": "post_amp", "role": "Modulation", "optional": True},
    {"key": "delay", "slot": "post_amp", "role": "Delay", "optional": True},
    {"key": "reverb", "slot": "post_amp", "role": "Reverb", "optional": True},
]

DISCLAIMER = (
    "ToneForge produces a tonal design, not a reproduction of any recording, and not a native "
    "AmpliTube preset file. Component names describe amp/cab/mic families and browser search terms "
    "because AmpliTube model availability varies by edition; pick the closest match in the AmpliTube "
    "browser and adjust by ear."
)
