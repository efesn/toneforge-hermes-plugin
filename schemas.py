"""Tool schemas: exactly what the model sees.

Descriptions are written for tool selection, not for documentation: each one says
what the tool does, when to use it, and - where it matters - what it does *not*
do (no silent port selection, no claim of verified parameter changes, no native
AmpliTube preset files).
"""

from __future__ import annotations

from typing import Any

_PRESET_PROP = {
    "type": "string",
    "description": "Preset name or slug, e.g. 'industrial-metal-drop-d-rhythm'.",
}


def _schema(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict:
    return {
        "name": name,
        "description": description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required or [],
        },
    }


CREATE_PRESET = _schema(
    "toneforge_create_preset",
    (
        "Design a complete guitar tone recipe from a natural-language-ish request: signal chain, amp and "
        "cabinet character, mic position, pedals, EQ, noise gate, gain/bass/mid/treble/presence/master and a "
        "short explanation. Use this whenever the user asks for a tone, a sound 'like' an artist or song, or "
        "a starting point for a genre. Returns a recipe to set up by hand in AmpliTube 5 - it does NOT "
        "change AmpliTube and does not write native AmpliTube preset files. Artist/song references are "
        "tonal inspiration only."
    ),
    {
        "genre": {
            "type": "string",
            "description": (
                "Genre or style, e.g. 'industrial metal', 'modern metalcore', 'thrash', 'hard rock', "
                "'classic rock', 'clean', 'ambient', 'lead'. Free text is matched against the profile library."
            ),
        },
        "reference": {
            "type": "string",
            "description": "Optional artist, song or album used as tonal inspiration (never a claim of exact reproduction).",
        },
        "tuning": {
            "type": "string",
            "description": "Guitar tuning, e.g. 'standard', 'Eb standard', 'drop D', 'drop C', 'drop B', '7-string'.",
        },
        "pickup": {
            "type": "string",
            "description": "Pickup type: humbucker, active humbucker, single coil, P-90, mini humbucker, piezo.",
        },
        "purpose": {
            "type": "string",
            "description": "Tone purpose: rhythm, lead, solo, clean, ambient or crunch.",
        },
        "gain_level": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100,
            "description": "Desired amp gain on ToneForge's normalised 0-100 scale (75 is 'high but not maxed').",
        },
        "instructions": {
            "type": "string",
            "description": (
                "Extra shaping in plain language, e.g. 'tight low end, keep note definition, more mids, "
                "less reverb'. Recognised: tighter/looser, more/less bass, mids, presence, treble, gain, "
                "mud, sustain, gate, delay, reverb, djent, doom, plus explicit 'set gain to 75'."
            ),
        },
        "name": {"type": "string", "description": "Optional preset name; otherwise generated from genre, tuning and purpose."},
        "save": {
            "type": "boolean",
            "description": "Also store the result in the preset library (default false: return the recipe only).",
        },
        "overwrite": {
            "type": "boolean",
            "description": "Only with save=true: allow replacing an existing preset of the same name.",
        },
    },
)

ADJUST_PRESET = _schema(
    "toneforge_adjust_preset",
    (
        "Modify an existing preset or tone recipe with a natural-language instruction ('make the low end "
        "tighter', 'reduce the gain slightly', 'add presence', 'less muddy', 'more mids', 'set gain to 80'). "
        "Returns the updated recipe, a precise before/after change list and an explanation. It does NOT "
        "change the stored preset unless save=true is passed explicitly."
    ),
    {
        "preset": {
            "type": "string",
            "description": "Name/slug of a stored preset, or 'current' to adjust the tone returned earlier in this conversation (pass it as 'config').",
        },
        "config": {
            "type": "object",
            "description": "Optional full tone object to adjust instead of a stored preset (use the 'tone' object from a previous call).",
        },
        "instructions": {
            "type": "string",
            "description": "The adjustment in plain language. Numeric overrides such as 'set gain to 75' are applied last.",
        },
        "gain_level": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Force the amp gain to this 0-100 value."},
        "purpose": {"type": "string", "description": "Re-voice the recipe for another purpose: rhythm, lead, solo, clean, ambient, crunch."},
        "tuning": {"type": "string", "description": "Re-tune the recipe's compensation, e.g. 'drop C'."},
        "save": {"type": "boolean", "description": "Persist the adjusted recipe, replacing the stored preset (default false)."},
        "save_as": {"type": "string", "description": "Save the adjusted recipe under a new name instead of overwriting."},
    },
    required=["instructions"],
)

SAVE_PRESET = _schema(
    "toneforge_save_preset",
    (
        "Store a tone recipe as a JSON preset in the local library, or duplicate an existing preset under a "
        "new name. Refuses to overwrite unless overwrite=true. These are ToneForge JSON presets, not native "
        "AmpliTube .at5p files."
    ),
    {
        "config": {"type": "object", "description": "The full tone object to store (the 'tone' object returned by toneforge_create_preset or toneforge_adjust_preset)."},
        "preset": {"type": "string", "description": "Alternatively: an existing preset to duplicate (requires name)."},
        "name": {"type": "string", "description": "Display name for the stored preset."},
        "description": {"type": "string", "description": "Optional one-line description."},
        "notes": {"type": "array", "items": {"type": "string"}, "description": "Optional free-form notes to keep with the preset."},
        "overwrite": {"type": "boolean", "description": "Replace an existing preset of the same name (default false)."},
    },
)

LIST_PRESETS = _schema(
    "toneforge_list_presets",
    "List the presets in the local ToneForge library, newest first, with their genre, tuning and version.",
    {},
)

GET_PRESET = _schema(
    "toneforge_get_preset",
    "Load one stored preset in full: parameters, signal chain, EQ, gate, notes and metadata.",
    {"preset": _PRESET_PROP},
    required=["preset"],
)

DELETE_PRESET = _schema(
    "toneforge_delete_preset",
    "Delete a stored preset from the local library. Requires confirm=true; deletion cannot be undone.",
    {
        "preset": _PRESET_PROP,
        "confirm": {"type": "boolean", "description": "Must be true - the user has agreed to delete this preset."},
    },
    required=["preset", "confirm"],
)

LIST_PROFILES = _schema(
    "toneforge_list_profiles",
    (
        "List the built-in tone profiles (industrial metal, modern metal, thrash, metalcore, hard rock, "
        "classic rock, clean, ambient, lead) with their defaults and starting parameters. Use it to show "
        "the user what exists before creating a tone."
    ),
    {
        "include_details": {
            "type": "boolean",
            "description": "Include amp/cab character, pedals and starting parameters for each profile.",
        }
    },
)

MIDI_STATUS = _schema(
    "toneforge_midi_status",
    (
        "Report the MIDI bridge state: which backend is in use (winmm stdlib driver or python-rtmidi), "
        "whether a port is selected, how many CC mappings exist and what to do next. Read-only."
    ),
    {},
)

LIST_MIDI_PORTS = _schema(
    "toneforge_list_midi_ports",
    (
        "List the MIDI output ports this machine exposes, flagging ports that look like virtual loopbacks "
        "(the ones that can feed AmpliTube). Read-only - it does not select or open anything."
    ),
    {},
)

SELECT_MIDI_PORT = _schema(
    "toneforge_select_midi_port",
    (
        "Choose which MIDI output port ToneForge sends to, by index or by name. The choice is persisted. "
        "Pick the loopback port that AmpliTube 5 also has as its MIDI input."
    ),
    {
        "port": {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": "Port index from toneforge_list_midi_ports, or a name such as 'ToneForge' or 'loopMIDI Port'.",
        },
        "backend": {"type": "string", "description": "Optional backend filter: winmm or rtmidi."},
    },
    required=["port"],
)

SEND_MIDI = _schema(
    "toneforge_send_midi",
    (
        "Send one raw MIDI Control Change message through the selected loopback port, e.g. CC 20 value 80 on "
        "channel 1. Use this for mappings you have not stored. Success means Windows accepted the bytes - it "
        "does not prove AmpliTube applied them."
    ),
    {
        "cc": {"type": "integer", "minimum": 0, "maximum": 127, "description": "Control Change number, 0-127."},
        "value": {"type": "integer", "minimum": 0, "maximum": 127, "description": "CC value, 0-127."},
        "channel": {"type": "integer", "minimum": 1, "maximum": 16, "description": "MIDI channel, 1-16 (default 1)."},
        "port": {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": "Optional one-off port index or name; defaults to the selected port.",
        },
        "backend": {"type": "string", "description": "Optional backend filter: winmm or rtmidi."},
    },
    required=["cc", "value"],
)

SET_PARAMETER = _schema(
    "toneforge_set_parameter",
    (
        "Set a mapped parameter by name, e.g. 'amp_gain' to 80. Looks up the user's CC mapping, converts the "
        "normalised 0-100 value into that mapping's CC range and sends the message. There is no default "
        "AmpliTube mapping: if the parameter is not mapped, the tool says so and suggests the CC assignment."
    ),
    {
        "parameter": {
            "type": "string",
            "description": "Mapping name or alias: amp_gain, amp_bass, amp_mid, amp_treble, amp_presence, amp_master, gate_threshold, gate_decay, od_drive, od_level, od_tone, delay_mix, reverb_mix (or 'gain', 'bass', 'mids', ...).",
        },
        "value": {
            "type": "number",
            "description": "Target value on the mapping's parameter range (normally 0-100, e.g. 80 means 80% of the knob's travel).",
        },
        "channel": {"type": "integer", "minimum": 1, "maximum": 16, "description": "Override the mapping's channel."},
        "port": {
            "anyOf": [{"type": "integer"}, {"type": "string"}],
            "description": "Optional one-off port index or name; defaults to the selected port.",
        },
    },
    required=["parameter", "value"],
)

MAP_PARAMETER = _schema(
    "toneforge_map_parameter",
    (
        "Record a MIDI CC assignment that the user made in AmpliTube's own 'Assign MIDI / Learn' dialog, so "
        "ToneForge knows which CC drives which parameter. Also installs ToneForge's suggested CC layout when "
        "seed_suggested=true. Nothing here is an AmpliTube default - the user's AmpliTube assignment is the "
        "source of truth."
    ),
    {
        "parameter": {"type": "string", "description": "Parameter name, e.g. amp_gain, amp_bass, amp_presence, gate_threshold."},
        "cc": {"type": "integer", "minimum": 0, "maximum": 127, "description": "The CC number the user assigned in AmpliTube."},
        "channel": {"type": "integer", "minimum": 1, "maximum": 16, "description": "MIDI channel the assignment listens on (default 1)."},
        "min": {"type": "integer", "minimum": 0, "maximum": 127, "description": "Lowest raw CC byte that reaches the parameter (default 0)."},
        "max": {"type": "integer", "minimum": 0, "maximum": 127, "description": "Highest raw CC byte that reaches the parameter (default 127)."},
        "param_min": {"type": "integer", "description": "Lowest value of the parameter's own range (default 0)."},
        "param_max": {"type": "integer", "description": "Highest value of the parameter's own range (default 100; set 50 if the user limited AmpliTube's Max to 50%)."},
        "invert": {"type": "boolean", "description": "Mirror the CC travel (AmpliTube Min 100% / Max 0%)."},
        "note": {"type": "string", "description": "Free-form reminder, e.g. 'Lead channel gain knob'."},
        "scope": {
            "type": "string",
            "description": "AmpliTube assignment scope: 'preset' (default - per-preset parameter assignment) or 'global' (preset switching, volume, wah, stomps only).",
        },
        "overwrite": {"type": "boolean", "description": "Replace an existing mapping for this parameter (default false)."},
        "seed_suggested": {
            "type": "boolean",
            "description": "Install ToneForge's suggested CC layout (amp_gain=20 ... reverb_mix=32) for every unmapped parameter. Not an AmpliTube default.",
        },
    },
    required=[],
)

LIST_MAPPINGS = _schema(
    "toneforge_list_mappings",
    "Show the stored parameter-to-CC mappings and which suggested parameters are still unmapped.",
    {},
)

REMOVE_MAPPING = _schema(
    "toneforge_remove_mapping",
    "Forget a stored parameter-to-CC mapping. Does not change anything inside AmpliTube.",
    {"parameter": {"type": "string", "description": "Mapping name to remove, e.g. amp_gain."}},
    required=["parameter"],
)

MIDI_PROBE = _schema(
    "toneforge_midi_probe",
    (
        "Send a short value sequence on one CC (0, 127, 64) to bind it during AmpliTube's MIDI Learn, or to "
        "confirm which control a CC is wired to by watching AmpliTube. Explicit user request only."
    ),
    {
        "cc": {"type": "integer", "minimum": 0, "maximum": 127, "description": "CC number to exercise."},
        "parameter": {"type": "string", "description": "Alternatively, a mapped parameter name whose CC should be exercised."},
        "channel": {"type": "integer", "minimum": 1, "maximum": 16, "description": "MIDI channel (default 1)."},
        "values": {
            "type": "array",
            "items": {"type": "integer", "minimum": 0, "maximum": 127},
            "description": "Sequence to send; default [0, 127, 64].",
        },
        "port": {"anyOf": [{"type": "integer"}, {"type": "string"}], "description": "Optional one-off port."},
    },
    required=[],
)

TOOLS: list[dict[str, Any]] = [
    CREATE_PRESET,
    ADJUST_PRESET,
    SAVE_PRESET,
    LIST_PRESETS,
    GET_PRESET,
    DELETE_PRESET,
    LIST_PROFILES,
    MIDI_STATUS,
    LIST_MIDI_PORTS,
    SELECT_MIDI_PORT,
    SEND_MIDI,
    SET_PARAMETER,
    MAP_PARAMETER,
    LIST_MAPPINGS,
    REMOVE_MAPPING,
    MIDI_PROBE,
]

_BY_NAME = {schema["name"]: schema for schema in TOOLS}


def get(name: str) -> dict[str, Any]:
    return _BY_NAME[name]
