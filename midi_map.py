"""User-defined MIDI CC mappings.

ToneForge never assumes that a given CC number controls a given AmpliTube
parameter. AmpliTube binds CCs through its own MIDI Learn / "Assign MIDI"
workflow, so the mapping table is owned by the user: this module stores what the
user *told* ToneForge they assigned, converts musical 0-100 values into that
mapping's CC range, and refuses to invent anything that is not in the table.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

from . import validation as V

SCHEMA_VERSION = 1

# Aliases so "set the amp gain" finds a mapping stored as "amp_gain" (and vice
# versa). These are ToneForge names, not AmpliTube names.
PARAM_ALIASES: dict[str, str] = {
    "gain": "amp_gain",
    "amp gain": "amp_gain",
    "distortion": "amp_gain",
    "drive": "amp_gain",
    "bass": "amp_bass",
    "low": "amp_bass",
    "mid": "amp_mid",
    "mids": "amp_mid",
    "middle": "amp_mid",
    "treble": "amp_treble",
    "high": "amp_treble",
    "presence": "amp_presence",
    "master": "amp_master",
    "volume": "amp_master",
    "master volume": "amp_master",
    "gate": "gate_threshold",
    "gate threshold": "gate_threshold",
    "gate decay": "gate_decay",
    "overdrive": "od_drive",
    "od drive": "od_drive",
    "od level": "od_level",
    "od tone": "od_tone",
    "delay": "delay_mix",
    "delay mix": "delay_mix",
    "reverb": "reverb_mix",
    "reverb mix": "reverb_mix",
}

# ToneForge's own suggested CC layout. It is documented as a convention to
# follow when assigning CCs inside AmpliTube - it is NOT an AmpliTube default.
SUGGESTED_MAPPINGS: dict[str, dict[str, Any]] = {
    "amp_gain": {"cc": 20, "channel": 1, "note": "Amplifier gain / drive knob"},
    "amp_bass": {"cc": 21, "channel": 1, "note": "Amplifier bass knob"},
    "amp_mid": {"cc": 22, "channel": 1, "note": "Amplifier mid knob"},
    "amp_treble": {"cc": 23, "channel": 1, "note": "Amplifier treble knob"},
    "amp_presence": {"cc": 24, "channel": 1, "note": "Amplifier presence knob"},
    "amp_master": {"cc": 25, "channel": 1, "note": "Amplifier master volume"},
    "gate_threshold": {"cc": 26, "channel": 1, "note": "Noise gate threshold"},
    "gate_decay": {"cc": 27, "channel": 1, "note": "Noise gate decay/release"},
    "od_drive": {"cc": 28, "channel": 1, "note": "Overdrive pedal drive"},
    "od_level": {"cc": 29, "channel": 1, "note": "Overdrive pedal level"},
    "od_tone": {"cc": 30, "channel": 1, "note": "Overdrive pedal tone"},
    "delay_mix": {"cc": 31, "channel": 1, "note": "Delay mix"},
    "reverb_mix": {"cc": 32, "channel": 1, "note": "Reverb mix"},
}

# AmpliTube 5 has two MIDI-control scopes (verified in the AmpliTube 5 manual,
# chapter 5): "Global" covers only preset next/previous, volume, wah, wharmonator
# and the 12 stomp bypasses; every other parameter assignment is "Preset" scope
# and only responds while that preset is loaded. Amp-knob mappings are therefore
# preset-scoped, which is why ToneForge records the scope with each mapping.
SCOPES = ("preset", "global")

_MAX_FILE_BYTES = 1_000_000


def canonical_name(name: str) -> str:
    """Resolve a user-supplied parameter name to a mapping key."""
    folded = V._fold(name).replace("-", " ").replace("_", " ")
    folded = " ".join(folded.split())
    if folded in PARAM_ALIASES:
        return PARAM_ALIASES[folded]
    return V.validate_mapping_name(folded.replace(" ", "_"))


def to_cc(value: int, mapping: dict[str, Any]) -> int:
    """Convert a 0-100 (or custom) musical value into this mapping's CC range."""
    param_min = int(mapping.get("param_min", 0))
    param_max = int(mapping.get("param_max", 100))
    if param_max <= param_min:
        raise V.ValidationError("mapping param_max must be greater than param_min")
    clamped = max(param_min, min(param_max, int(value)))
    ratio = (clamped - param_min) / (param_max - param_min)
    if mapping.get("invert"):
        ratio = 1.0 - ratio
    low, high = int(mapping["min"]), int(mapping["max"])
    return int(round(low + ratio * (high - low)))


class MappingStore:
    """JSON-backed mapping table at ``<data dir>/midi_map.json``."""

    def __init__(self, root: Optional[Path] = None) -> None:
        from . import preset_store  # local import keeps module import order simple

        self.root = Path(root) if root is not None else preset_store.data_dir()
        self.path = self.root / "midi_map.json"

    # -- persistence ------------------------------------------------------- #
    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": SCHEMA_VERSION, "mappings": {}}
        if self.path.stat().st_size > _MAX_FILE_BYTES:
            raise V.ToneForgeError("midi_map.json is unexpectedly large; refusing to load it")
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise V.ToneForgeError(f"midi_map.json is not valid JSON: {exc}") from None
        if not isinstance(data, dict) or not isinstance(data.get("mappings", {}), dict):
            raise V.ToneForgeError("midi_map.json has an unexpected shape")
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("mappings", {})
        return data

    def _write(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        handle = None
        temp_name = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".midi_map.", suffix=".tmp", dir=str(self.root))
            handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            handle = None
            os.replace(temp_name, self.path)
            temp_name = None
        finally:
            if handle is not None:
                handle.close()
            if temp_name is not None and os.path.exists(temp_name):
                os.unlink(temp_name)

    # -- public API -------------------------------------------------------- #
    def all(self) -> dict[str, dict[str, Any]]:
        return dict(self._read()["mappings"])

    def get(self, name: str) -> Optional[dict[str, Any]]:
        key = canonical_name(name)
        mappings = self._read()["mappings"]
        return dict(mappings[key]) if key in mappings else None

    def add(
        self,
        name: str,
        cc: int,
        *,
        channel: int = 1,
        minimum: int = 0,
        maximum: int = 127,
        param_min: int = 0,
        param_max: int = 100,
        invert: bool = False,
        note: str = "",
        scope: str = "preset",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        key = canonical_name(name)
        data = self._read()
        if key in data["mappings"] and not overwrite:
            current = data["mappings"][key]
            raise V.ConflictError(
                f"{key} is already mapped to CC {current['cc']} on channel {current['channel']}; "
                "pass overwrite=true to change it"
            )
        entry = {
            "cc": cc,
            "channel": channel,
            "min": minimum,
            "max": maximum,
            "param_min": param_min,
            "param_max": param_max,
            "invert": bool(invert),
            "note": note,
            "scope": scope,
            "assigned_in": "user",
        }
        self._validate_entry(key, entry)
        data["mappings"][key] = entry
        self._write(data)
        return {key: entry}

    def remove(self, name: str) -> dict[str, Any]:
        key = canonical_name(name)
        data = self._read()
        if key not in data["mappings"]:
            raise V.NotFoundError(f"No mapping named {key!r}")
        entry = data["mappings"].pop(key)
        self._write(data)
        return {key: entry}

    def seed_suggested(self, *, overwrite: bool = False) -> list[str]:
        """Install ToneForge's conventional CC layout for keys that are unset."""
        data = self._read()
        added: list[str] = []
        for key, spec in SUGGESTED_MAPPINGS.items():
            if key in data["mappings"] and not overwrite:
                continue
            entry = {
                "cc": spec["cc"],
                "channel": spec["channel"],
                "min": 0,
                "max": 127,
                "param_min": 0,
                "param_max": 100,
                "invert": False,
                "note": spec["note"],
                "scope": "preset",
                "assigned_in": "toneforge-convention",
            }
            data["mappings"][key] = entry
            added.append(key)
        if added:
            self._write(data)
        return added

    def _validate_entry(self, key: str, entry: dict[str, Any]) -> None:
        V.validate_mapping_name(key)
        V.coerce_int(entry["cc"], "cc", lo=0, hi=127)
        V.coerce_int(entry["channel"], "channel", lo=1, hi=16)
        V.coerce_int(entry["min"], "min", lo=0, hi=127)
        V.coerce_int(entry["max"], "max", lo=0, hi=127)
        V.coerce_int(entry["param_min"], "param_min", lo=0, hi=127)
        V.coerce_int(entry["param_max"], "param_max", lo=1, hi=127)
        if entry.get("scope") not in SCOPES:
            raise V.ValidationError("mapping scope must be 'preset' or 'global'")
        if entry["min"] > entry["max"]:
            raise V.ValidationError("mapping min must be <= max")
        if entry["param_min"] >= entry["param_max"]:
            raise V.ValidationError("mapping param_min must be < param_max")


def describe(entry: dict[str, Any], name: str) -> str:
    """Compact human description of one mapping."""
    direction = " (inverted)" if entry.get("invert") else ""
    return (
        f"{name}: CC {entry['cc']} ch {entry['channel']}, "
        f"value {entry.get('param_min', 0)}-{entry.get('param_max', 100)} -> "
        f"CC {entry['min']}-{entry['max']}{direction}"
        + (f" [{entry.get('scope')} scope]" if entry.get("scope") else "")
    )
