"""Tool handlers.

Contract (from the Hermes plugin guide): every handler takes ``args: dict`` plus
``**kwargs`` and returns a JSON *string* - success and failure alike - and never
raises. A small decorator enforces that, so individual handlers can read like
plain functions.
"""

from __future__ import annotations

import functools
import json
import logging
import sys
import threading
from typing import Any, Callable, Optional

from . import midi_io, midi_map, preset_store, tone_engine, tone_profiles
from . import validation as V

logger = logging.getLogger(__name__)

_CONFIG: dict[str, Any] = {"midi_backend": "auto", "default_channel": 1}
_service_lock = threading.Lock()
_service: Optional[midi_io.MidiService] = None


def configure(*, midi_backend: Optional[str] = None, default_channel: Optional[int] = None) -> None:
    """Apply plugin settings. Called once from ``register(ctx)``."""
    global _service
    with _service_lock:
        if midi_backend:
            _CONFIG["midi_backend"] = str(midi_backend)
        if default_channel is not None:
            _CONFIG["default_channel"] = int(default_channel)
        _service = None


def midi_service() -> midi_io.MidiService:
    """One service instance per process so open device handles are reused."""
    global _service
    with _service_lock:
        if _service is None:
            _service = midi_io.MidiService(
                backend_preference=_CONFIG["midi_backend"],
                default_channel=_CONFIG["default_channel"],
            )
        return _service


def store() -> preset_store.PresetStore:
    return preset_store.PresetStore()


def mappings() -> midi_map.MappingStore:
    return midi_map.MappingStore()


# --------------------------------------------------------------------------- #
# Plumbing
# --------------------------------------------------------------------------- #
def tool(fn: Callable[..., dict]) -> Callable[..., str]:
    """Wrap a handler: validate args, serialize the result, never raise."""

    @functools.wraps(fn)
    def wrapper(args: Any = None, **kwargs: Any) -> str:
        try:
            if args is None:
                args = {}
            if not isinstance(args, dict):
                raise V.ValidationError("tool arguments must be a JSON object")
            payload = fn(args, **kwargs)
            if not isinstance(payload, dict):
                payload = {"ok": True, "result": payload}
            payload.setdefault("ok", True)
            return json.dumps(payload, ensure_ascii=False)
        except V.ToneForgeError as exc:
            logger.info("ToneForge refused a call: %s", exc)
            return json.dumps(
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__}, ensure_ascii=False
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("ToneForge tool failed unexpectedly")
            return json.dumps(
                {"ok": False, "error": f"unexpected failure: {exc}", "error_type": type(exc).__name__},
                ensure_ascii=False,
            )

    return wrapper


def _int(args: dict, key: str, *, lo: int, hi: int, default: Optional[int] = None) -> Optional[int]:
    return V.coerce_int(args.get(key), key, lo=lo, hi=hi, default=default)


def _bool(args: dict, key: str, default: bool = False) -> bool:
    value = args.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    if value is None:
        return default
    raise V.ValidationError(f"{key} must be true or false")


def _check_config(cfg: Any) -> dict:
    """Minimal structural check so a partial object fails with a useful message."""
    cfg = V.ensure_mapping(cfg, "config")
    required = ("params", "eq", "gate", "pedals", "space", "amp", "cabinet", "mic")
    missing = [key for key in required if key not in cfg]
    if missing:
        raise V.ValidationError(
            "config does not look like a ToneForge tone (missing: "
            + ", ".join(missing)
            + "). Pass the 'tone' object returned by toneforge_create_preset."
        )
    return cfg


_HOW_TO_APPLY = [
    "Build the chain in AmpliTube 5 Standalone in the listed order; ToneForge cannot insert models for you.",
    "Pick the closest amp/cab/mic in the AmpliTube browser using the search terms, then set the knobs to the 0-100 values.",
    "Set the 7-band EQ on an AmpliTube EQ pedal (or approximate the dB moves with the amp's tone stack).",
    "Save it inside AmpliTube as a normal AmpliTube preset; ToneForge stores its own JSON copy alongside it.",
]


# --------------------------------------------------------------------------- #
# Tone design
# --------------------------------------------------------------------------- #
@tool
def create_preset(args: dict, **_: Any) -> dict:
    gain_level = _int(args, "gain_level", lo=0, hi=100)
    cfg = tone_engine.build_tone(
        genre=args.get("genre"),
        reference=args.get("reference"),
        tuning=args.get("tuning"),
        pickup=args.get("pickup"),
        purpose=args.get("purpose"),
        gain_level=gain_level,
        instructions=args.get("instructions"),
        name=args.get("name"),
    )
    result: dict[str, Any] = {
        "tone": cfg,
        "applies_automatically": False,
        "how_to_apply": _HOW_TO_APPLY,
    }
    if _bool(args, "save"):
        record = store().save(
            cfg,
            name=cfg["name"],
            overwrite=_bool(args, "overwrite"),
        )
        result["saved"] = {
            "slug": record["slug"],
            "name": record["name"],
            "version": record["version"],
            "path": str(store().path_for(record["slug"])),
        }
    result["next_steps"] = _next_steps(saved="saved" in result)
    return result


def _next_steps(*, saved: bool = False) -> list[str]:
    steps = []
    if not saved:
        steps.append("Say 'save it' (or call toneforge_save_preset) to keep this in the preset library.")
    steps.append(
        "In AmpliTube, right-click a knob, choose 'Assign MIDI', then Learn: ToneForge can then send that CC "
        "once you record it with toneforge_map_parameter."
    )
    steps.append("toneforge_midi_status shows whether the MIDI bridge is ready before you rely on it.")
    return steps


@tool
def adjust_preset(args: dict, **_: Any) -> dict:
    instructions = V.require_text(args.get("instructions"), "instructions", max_len=2000, required=True)
    assert instructions is not None

    base: dict[str, Any]
    stored_record: Optional[dict[str, Any]] = None
    if isinstance(args.get("config"), dict):
        base = _check_config(args["config"])
    elif args.get("preset"):
        stored_record = store().load(str(args["preset"]))
        base = _check_config(stored_record.get("config") or {})
    else:
        raise V.ValidationError(
            "pass either 'preset' (a stored preset name) or 'config' (the tone object from the previous call)"
        )

    updated, changes, explanations = tone_engine.adjust_tone(
        base,
        instructions,
        gain_level=_int(args, "gain_level", lo=0, hi=100),
        purpose=args.get("purpose"),
        tuning=args.get("tuning"),
    )

    result: dict[str, Any] = {
        "tone": updated,
        "changes": changes,
        "explanation": explanations,
        "applies_automatically": False,
    }

    save_flag = _bool(args, "save")
    save_as = V.require_text(args.get("save_as"), "save_as", max_len=80)
    if save_flag or save_as:
        target_name = save_as or updated["name"]
        record = store().save(
            updated,
            name=target_name,
            overwrite=bool(stored_record) and not save_as,
        )
        result["saved"] = {
            "slug": record["slug"],
            "name": record["name"],
            "version": record["version"],
            "path": str(store().path_for(record["slug"])),
        }
        updated["name"] = record["name"]
    else:
        result["note"] = (
            "The stored preset was NOT modified. Pass save=true to replace "
            + (f"'{stored_record.get('name')}'" if stored_record else "a preset")
            + ", or save_as='new name' to keep both."
        )
    return result


@tool
def list_profiles(args: dict, **_: Any) -> dict:
    details = _bool(args, "include_details")
    profiles = []
    for key, profile in tone_profiles.PROFILES.items():
        item: dict[str, Any] = {
            "key": key,
            "label": profile["label"],
            "default_tuning": tone_profiles.TUNINGS[profile["default_tuning"]]["label"],
            "default_purpose": tone_profiles.PURPOSES[profile["default_purpose"]]["label"],
            "params": dict(profile["params"]),
        }
        if details:
            item["amp"] = profile["amp"]
            item["cabinet"] = profile["cabinet"]
            item["pedals"] = [pedal["type"] for pedal in profile["pedals"]]
            item["aliases"] = profile["aliases"][:8]
        profiles.append(item)
    return {
        "count": len(profiles),
        "profiles": profiles,
        "tunings": [spec["label"] for spec in tone_profiles.TUNINGS.values()],
        "purposes": [spec["label"] for spec in tone_profiles.PURPOSES.values()],
        "note": "Profiles describe amp and cab *families*, never specific AmpliTube model names.",
    }


# --------------------------------------------------------------------------- #
# Preset library
# --------------------------------------------------------------------------- #
@tool
def save_preset(args: dict, **_: Any) -> dict:
    if isinstance(args.get("config"), dict):
        cfg = _check_config(args["config"])
    elif args.get("preset"):
        source = store().load(str(args["preset"]))
        cfg = _check_config(source.get("config") or {})
    else:
        raise V.ValidationError("pass 'config' (a tone object) or 'preset' (an existing preset to duplicate)")

    name = V.require_text(args.get("name"), "name", max_len=80) or cfg.get("name")
    if isinstance(args.get("config"), dict) and args.get("preset") and not args.get("name"):
        raise V.ValidationError("duplicating a preset needs a new 'name'")

    notes = args.get("notes")
    if notes is not None:
        notes = [str(V.require_text(item, "note", max_len=280)) for item in V.ensure_list(notes, "notes")]

    record = store().save(
        cfg,
        name=name,
        description=V.require_text(args.get("description"), "description", max_len=280),
        notes=notes,
        overwrite=_bool(args, "overwrite"),
    )
    return {
        "saved": {
            "slug": record["slug"],
            "name": record["name"],
            "version": record["version"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "path": str(store().path_for(record["slug"])),
        },
        "format": "ToneForge JSON preset (not a native AmpliTube .at5p file)",
    }


@tool
def list_presets(args: dict, **_: Any) -> dict:
    items = store().list()
    return {
        "count": len(items),
        "presets": items,
        "library": str(store().root),
        "note": "Load one with toneforge_get_preset." if items else (
            "The library is empty. Create a tone with toneforge_create_preset save=true."
        ),
    }


@tool
def get_preset(args: dict, **_: Any) -> dict:
    name = V.require_text(args.get("preset"), "preset", max_len=120, required=True)
    assert name is not None
    record = store().load(name)
    return {
        "preset": {
            "slug": record.get("slug"),
            "name": record.get("name"),
            "description": record.get("description"),
            "version": record.get("version"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "notes": record.get("notes", []),
        },
        "tone": record.get("config"),
    }


@tool
def delete_preset(args: dict, **_: Any) -> dict:
    if not _bool(args, "confirm"):
        raise V.ValidationError(
            "delete requires confirm=true: ask the user to confirm, then call again with confirm=true"
        )
    name = V.require_text(args.get("preset"), "preset", max_len=120, required=True)
    assert name is not None
    removed = store().delete(name, confirm=True)
    return {"deleted": removed, "note": "Removed from the local library only; AmpliTube is untouched."}


# --------------------------------------------------------------------------- #
# MIDI bridge
# --------------------------------------------------------------------------- #
@tool
def midi_status(args: dict, **_: Any) -> dict:
    service = midi_service()
    backends = {
        midi_io.BACKEND_WINMM: {
            "available": midi_io.WinMMBackend.available(),
            "reason": midi_io.WinMMBackend.unavailable_reason(),
            "kind": "stdlib ctypes (no dependency)",
        },
        midi_io.BACKEND_RTMIDI: {
            "available": midi_io.RtMidiBackend.available(),
            "reason": midi_io.RtMidiBackend.unavailable_reason(),
            "kind": "optional python-rtmidi",
        },
    }
    active = service.backend_name()
    selected = service.read_config().get("port")
    mapping_table = mappings().all()

    blockers: list[str] = []
    if active is None:
        blockers.append("No MIDI backend is available on this machine.")
    if not selected:
        blockers.append("No output port is selected yet (toneforge_select_midi_port).")
    if not mapping_table:
        blockers.append("No CC mappings are stored (toneforge_map_parameter), so named parameters cannot be set.")

    port_count = 0
    if active is not None:
        try:
            port_count = len(service.list_ports().get("ports", []))
        except V.ToneForgeError:
            port_count = 0

    return {
        "platform": sys.platform,
        "active_backend": active,
        "backends": backends,
        "ports_available": port_count,
        "selected_port": selected,
        "mappings": {
            "count": len(mapping_table),
            "parameters": sorted(mapping_table),
        },
        "default_channel": _CONFIG["default_channel"],
        "data_dir": str(preset_store.data_dir()),
        "ready": not blockers,
        "blockers": blockers,
        "amplitube_setup": [
            "Settings -> Audio/MIDI -> MIDI Input: select the loopback port (AmpliTube 5 manual, ch. 2.2).",
            "Settings -> Control -> Control Change: the MIDI Channel display must match ToneForge's channel, 1-16 (ch. 5.3).",
            "Right-click a knob -> Assign MIDI -> [parameter] -> Learn, then send that CC to bind it (ch. 5.2).",
            "Assignments made this way are per-preset (Preset scope). Global scope covers only preset switching, "
            "volume, wah, wharmonator and the 12 stomp bypasses (ch. 5).",
            "Leave AmpliTube's Min/Max at 0%/100% and Curve at 5 (linear) to match the mapping ToneForge assumes (ch. 5.3).",
        ],
        "explain": (
            "ToneForge sends CC messages to a port you select. AmpliTube only reacts to CCs you assigned "
            "inside its own MIDI Learn dialog, so the mapping table describes the user's assignment, not "
            "an AmpliTube default."
        ),
    }


@tool
def list_midi_ports(args: dict, **_: Any) -> dict:
    listed = midi_service().list_ports()
    if listed.get("ok"):
        listed["next"] = (
            "Pick the virtual loopback port that AmpliTube also has selected as its MIDI input, then call "
            "toneforge_select_midi_port."
        )
    return listed


@tool
def select_midi_port(args: dict, **_: Any) -> dict:
    backend = V.require_text(args.get("backend"), "backend", max_len=16)
    if backend is not None:
        backend = backend.lower()
        if backend not in midi_io.SUPPORTED_BACKENDS:
            raise V.ValidationError("backend must be 'winmm' or 'rtmidi'")
    port = args.get("port")
    if port is None:
        raise V.ValidationError("port is required (index or name from toneforge_list_midi_ports)")
    result = midi_service().select_port(port=port, backend=backend)
    result["note"] = (
        "Selection saved. AmpliTube must be listening to this same port (Settings -> Audio/MIDI -> MIDI input)."
    )
    return result


@tool
def send_midi(args: dict, **_: Any) -> dict:
    cc = _int(args, "cc", lo=0, hi=127)
    value = _int(args, "value", lo=0, hi=127)
    if cc is None or value is None:
        raise V.ValidationError("cc and value are required")
    channel = _int(args, "channel", lo=1, hi=16, default=_CONFIG["default_channel"]) or 1
    return midi_service().send_cc(
        channel=channel,
        cc=cc,
        value=value,
        port=args.get("port"),
        backend=V.require_text(args.get("backend"), "backend", max_len=16),
    )


@tool
def set_parameter(args: dict, **_: Any) -> dict:
    name = V.require_text(args.get("parameter"), "parameter", max_len=64, required=True)
    assert name is not None
    value = V.coerce_float(args.get("value"), "value", lo=0, hi=100)
    if value is None:
        raise V.ValidationError("value is required (0-100)")

    key = midi_map.canonical_name(name)
    table = mappings()
    entry = table.get(key)
    if entry is None:
        suggestion = midi_map.SUGGESTED_MAPPINGS.get(key, {}).get("cc")
        raise V.NotFoundError(
            f"{key} has no MIDI mapping, so ToneForge will not send anything. Assign a CC to that control in "
            "AmpliTube (right-click the knob -> Assign MIDI -> Learn), then record it with "
            f"toneforge_map_parameter(parameter='{key}', cc=<number>)."
            + (f" ToneForge's suggested CC for {key} is {suggestion}." if suggestion else "")
        )

    cc_value = midi_map.to_cc(int(round(value)), entry)
    channel = _int(args, "channel", lo=1, hi=16, default=int(entry["channel"])) or int(entry["channel"])
    result = midi_service().send_cc(
        channel=channel,
        cc=int(entry["cc"]),
        value=cc_value,
        port=args.get("port"),
    )
    result.update(
        {
            "parameter": key,
            "parameter_value": int(value) if float(value).is_integer() else value,
            "mapping": {
                "cc": entry["cc"],
                "channel": entry["channel"],
                "min": entry["min"],
                "max": entry["max"],
                "param_min": entry.get("param_min", 0),
                "param_max": entry.get("param_max", 100),
                "invert": bool(entry.get("invert")),
                "scope": entry.get("scope", "preset"),
            },
            "conversion": f"{value:g}/{entry.get('param_max', 100)} -> CC {cc_value}",
            "mapping_source": entry.get("assigned_in", "user"),
        }
    )
    if entry.get("scope") == "preset":
        result["scope_note"] = (
            "This is an AmpliTube Preset-level assignment: it only responds while that AmpliTube preset "
            "is loaded. Assign it again on other presets, or use a Global assignment for volume/wah/stomps."
        )
    if entry.get("assigned_in") == "toneforge-convention":
        result["warning"] = (
            "This CC comes from ToneForge's suggested layout, not from AmpliTube. Unless you assigned the "
            "same CC in AmpliTube's MIDI Learn dialog, nothing will move."
        )
    return result


@tool
def map_parameter(args: dict, **_: Any) -> dict:
    table = mappings()
    result: dict[str, Any] = {}
    seed = _bool(args, "seed_suggested")
    if seed:
        added = table.seed_suggested(overwrite=_bool(args, "overwrite"))
        result["seeded"] = {
            "added": added,
            "count": len(added),
            "note": (
                "ToneForge's suggested CC layout was stored. It is a convention for you to follow inside "
                "AmpliTube's MIDI Learn, NOT an AmpliTube default - nothing works until you assign the same "
                "CCs there."
            ),
        }

    parameter = V.require_text(args.get("parameter"), "parameter", max_len=64)
    if parameter is None:
        if not seed:
            raise V.ValidationError(
                "pass 'parameter' plus 'cc' to store one mapping, or seed_suggested=true for the whole layout"
            )
        result["mappings"] = table.all()
        return result

    cc = _int(args, "cc", lo=0, hi=127)
    if cc is None:
        raise V.ValidationError("cc is required (0-127)")
    key = midi_map.canonical_name(parameter)
    added = table.add(
        key,
        cc,
        channel=_int(args, "channel", lo=1, hi=16, default=1) or 1,
        minimum=_int(args, "min", lo=0, hi=127, default=0) or 0,
        maximum=_int(args, "max", lo=0, hi=127, default=127) or 127,
        param_min=_int(args, "param_min", lo=0, hi=127, default=0) or 0,
        param_max=_int(args, "param_max", lo=1, hi=127, default=100) or 100,
        invert=_bool(args, "invert"),
        note=V.require_text(args.get("note"), "note", max_len=120) or "",
        scope=V.normalize_choice(
            args.get("scope"), "scope", {"preset": "preset", "global": "global"}, default="preset"
        ),
        overwrite=_bool(args, "overwrite"),
    )
    result["mapping"] = added
    result["mappings"] = table.all()
    return result


@tool
def list_mappings(args: dict, **_: Any) -> dict:
    table = mappings().all()
    missing = [key for key in midi_map.SUGGESTED_MAPPINGS if key not in table]
    return {
        "count": len(table),
        "mappings": {
            key: {**entry, "description": midi_map.describe(entry, key)} for key, entry in sorted(table.items())
        },
        "unmapped_suggested": missing,
        "suggested_layout": (
            {key: spec["cc"] for key, spec in midi_map.SUGGESTED_MAPPINGS.items()} if missing else {}
        ),
        "note": (
            "Mappings describe CC assignments made inside AmpliTube. ToneForge never assumes a CC number "
            "controls a parameter."
        ),
    }


@tool
def remove_mapping(args: dict, **_: Any) -> dict:
    name = V.require_text(args.get("parameter"), "parameter", max_len=64, required=True)
    assert name is not None
    removed = mappings().remove(name)
    return {
        "removed": removed,
        "note": "Only ToneForge's record was removed; the assignment inside AmpliTube is unchanged.",
    }


@tool
def midi_probe(args: dict, **_: Any) -> dict:
    channel = _int(args, "channel", lo=1, hi=16, default=_CONFIG["default_channel"]) or 1
    cc = _int(args, "cc", lo=0, hi=127)

    if cc is None:
        parameter = V.require_text(args.get("parameter"), "parameter", max_len=64)
        if parameter is None:
            raise V.ValidationError("pass 'cc' or a mapped 'parameter' to probe")
        entry = mappings().get(midi_map.canonical_name(parameter))
        if entry is None:
            raise V.NotFoundError(
                f"no mapping stored for {parameter!r}; pass the raw 'cc' number instead"
            )
        cc = int(entry["cc"])
        channel = int(entry["channel"])

    values = args.get("values")
    if values is None:
        sequence = (0, 127, 64)
    else:
        sequence = tuple(
            int(V.coerce_int(value, "values", lo=0, hi=127)) for value in V.ensure_list(values, "values")
        )
        if not sequence:
            raise V.ValidationError("values must contain at least one integer 0-127")
        if len(sequence) > 8:
            raise V.ValidationError("values is limited to 8 entries")

    result = midi_service().probe(
        channel=channel, cc=cc, port=args.get("port"), values=sequence
    )
    result["parameter"] = args.get("parameter")
    return result


HANDLERS: dict[str, Callable[..., str]] = {
    "toneforge_create_preset": create_preset,
    "toneforge_adjust_preset": adjust_preset,
    "toneforge_save_preset": save_preset,
    "toneforge_list_presets": list_presets,
    "toneforge_get_preset": get_preset,
    "toneforge_delete_preset": delete_preset,
    "toneforge_list_profiles": list_profiles,
    "toneforge_midi_status": midi_status,
    "toneforge_list_midi_ports": list_midi_ports,
    "toneforge_select_midi_port": select_midi_port,
    "toneforge_send_midi": send_midi,
    "toneforge_set_parameter": set_parameter,
    "toneforge_map_parameter": map_parameter,
    "toneforge_list_mappings": list_mappings,
    "toneforge_remove_mapping": remove_mapping,
    "toneforge_midi_probe": midi_probe,
}
