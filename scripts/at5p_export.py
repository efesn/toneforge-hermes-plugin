#!/usr/bin/env python3
"""Export a ToneForge JSON preset as a native AmpliTube 5 `.at5p` file.

This is the clone-and-rewrite path: an existing `.at5p` supplies the chain skeleton and the
model GUIDs, the ToneForge preset supplies the numbers. Nothing here guesses a model your
install does not have - every GUID written is checked against the presets already on disk.

Usage
-----
    python scripts/at5p_export.py --preset rammstein-sonne-main-riff
    python scripts/at5p_export.py --preset sonne-demo --template "C:/.../SupeReady.at5p" \
        --amp-guid 8fe96936-5178-4950-9b80-d89c32534bad --out "C:/.../My Tone.at5p"

After writing, AmpliTube registers the file the next time it starts (its browser is fed by
Presets.db, not by the folder).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

DEFAULT_PRESET_DIR = Path.home() / "Documents" / "IK Multimedia" / "AmpliTube 5" / "Presets" / "AmpliTube 5"
EMPTY_GUID = "773b8ea7-b54a-4a3c-99df-ffbbf6d29271"   # AmpliTube's "no model" marker
SKIP_DIRS = {"__pycache__"}

GAIN_KEYS = ("preamp", "gain", "leadchvolume", "ch1gain", "ch3gain", "volumech")
BASS_KEYS = ("bass",)
MID_KEYS = ("middle", "mid")
TREBLE_KEYS = ("treble",)
PRESENCE_KEYS = ("presence", "depth")
MASTER_KEYS = ("master", "volume", "leadvolume")
EQ_BANDS = (100, 200, 400, 800, 1600, 3200, 6400)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def preset_library() -> Path:
    override = os.environ.get("TONEFORGE_DATA_DIR")
    if override:
        return Path(override) / "presets"
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "hermes"
    return base / "plugin-data" / "tone-forge" / "presets"


def load_preset(name: str) -> dict:
    lib = preset_library()
    direct = lib / f"{name}.json"
    if direct.exists():
        return json.loads(direct.read_text(encoding="utf-8"))
    for path in sorted(lib.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("name", "").casefold() == name.casefold():
            return doc
    raise SystemExit(f"no ToneForge preset named {name!r} in {lib}")


def at5p_files(preset_dir: Path) -> list[Path]:
    if not preset_dir.is_dir():
        raise SystemExit(f"not a directory: {preset_dir}")
    return sorted(p for p in preset_dir.rglob("*.at5p") if p.is_file())


def guid_pool(files: list[Path]) -> set[str]:
    pool: set[str] = set()
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for el in root.iter():
            for key, value in el.attrib.items():
                if len(value) == 36 and (key.startswith("Stomp") or key in ("Model", "CabModel")):
                    pool.add(value)
    return pool


def pick_template(files: list[Path]) -> Path:
    """Prefer a preset that already has an amp, a cab and at least one rack effect."""
    best, best_score = None, -1
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        score = 0
        amp = root.find("AmpA")
        if amp is not None and amp.get("Model"):
            score += 2
        cab = root.find("CabA")
        if cab is not None and cab.get("CabModel"):
            score += 1
        for rack in ("RackA", "RackB"):
            el = root.find(rack)
            if el is not None and any(el.get(f"Stomp{i}", EMPTY_GUID) != EMPTY_GUID for i in range(2)):
                score += 1
        if score > best_score:
            best, best_score = path, score
    if best is None:
        raise SystemExit("no usable .at5p template found")
    return best


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
def _find_param(amp_el: ET.Element, keys: tuple[str, ...]) -> str | None:
    """Find the amp parameter whose name matches one of *keys* (case-insensitive)."""
    best = None
    for el in amp_el.iter("Amp"):
        for name in el.attrib:
            lowered = name.casefold()
            for key in keys:
                if key in lowered:
                    if best is None or len(name) < len(best):
                        best = name
                    break
    return best


def params_for_model(files: list[Path], guid: str) -> dict[str, str] | None:
    """Reuse the exact parameter names another preset already uses for this amp model.

    Switching the model GUID without switching the parameter names would load with every
    knob at AmpliTube's default - a silent, wrong-sounding result.
    """
    for path in files:
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        for tag in ("AmpA", "AmpB", "AmpC"):
            holder = root.find(tag)
            if holder is None or holder.get("Model") != guid:
                continue
            amp = holder.find("Amp")
            if amp is not None and amp.attrib:
                return dict(amp.attrib)
    return None


def apply_amp(root: ET.Element, tone: dict, names: dict[str, str] | None = None) -> dict[str, float]:
    """Write the recipe's 0-100 params into the amp, using *names* when the model changed."""
    params = tone["params"]
    written: dict[str, float] = {}
    wanted = {
        "gain": (params.get("gain"), GAIN_KEYS),
        "bass": (params.get("bass"), BASS_KEYS),
        "mid": (params.get("mid"), MID_KEYS),
        "treble": (params.get("treble"), TREBLE_KEYS),
        "presence": (params.get("presence"), PRESENCE_KEYS),
        "master": (params.get("master"), MASTER_KEYS),
    }
    for tag in ("AmpA", "AmpB", "AmpC"):
        holder = root.find(tag)
        if holder is None:
            continue
        amp = holder.find("Amp")
        if amp is None:
            continue
        if names is not None:
            amp.clear()
            for name, value in names.items():
                amp.set(name, value)
        for label, (value, keys) in wanted.items():
            if value is None:
                continue
            name = _find_param(holder, keys)
            if not name:
                continue
            scaled = round(float(value) / 10.0, 3)
            amp.set(name, f"{scaled:.3f}")
            written[f"{tag}.{label}"] = scaled
        break  # only the primary amp gets the recipe; B/C stay neutral
    return written


def apply_eq(root: ET.Element, tone: dict) -> str:
    """Set the 7-band graphic if the template carries one, else leave it parked."""
    eq = tone.get("eq") or {}
    bands = {int(b["hz"]): float(b["db"]) for b in eq.get("bands", [])}
    for slot_tag in ("StompA1", "LoopFxA", "StompB1", "LoopFxB"):
        holder = root.find(slot_tag)
        if holder is None:
            continue
        for i in range(8):
            guid = holder.get(f"Stomp{i}")
            slot = holder.find(f"Slot{i}")
            if guid is None or guid == EMPTY_GUID or slot is None:
                continue
            if not any(band in slot.attrib for band in ("Band100", "Band800")):
                continue
            for hz in EQ_BANDS:
                key = f"Band{hz}" if hz != 1600 else "Band1600"
                if key in slot.attrib and hz in bands:
                    # the fader's unity point is undocumented; only the sign is applied
                    slot.set(key, "5.0" if bands[hz] == 0 else ("6.0" if bands[hz] > 0 else "4.0"))
            slot.set("Bypass", "0")
            return f"{slot_tag}.Slot{i}"
    return "none (template has no 7-band graphic; the amp tone stack carries the curve)"


def apply_gate(root: ET.Element, tone: dict) -> bool:
    gate = tone.get("gate") or {}
    if not gate.get("enabled"):
        return False
    for holder_tag in ("StompA1", "StompB1"):
        holder = root.find(holder_tag)
        if holder is None:
            continue
        for i in range(8):
            slot = holder.find(f"Slot{i}")
            if slot is not None and "Threshold" in slot.attrib:
                # AmpliTube stores a linear amplitude, not dB; map -60..0 dB into 0.0002..0.02
                db = float(gate.get("threshold_db", -50.0))
                amp = max(0.0002, min(0.02, 0.02 * (10 ** ((db + 60) / 40.0)) / 10))
                slot.set("Threshold", f"{amp:.6f}")
                slot.set("Release", str(int(gate.get("decay_ms", 200))))
                slot.set("Bypass", "0")
                return True
    return False


def apply_space(root: ET.Element, tone: dict) -> dict[str, str]:
    space = tone.get("space") or {}
    out = {}
    rev = float(space.get("reverb_mix", 0.0)) * 100
    dly = float(space.get("delay_mix", 0.0)) * 100
    for holder_tag in ("RackA", "RackB", "RackC", "LoopFxA", "LoopFxB"):
        holder = root.find(holder_tag)
        if holder is None:
            continue
        for i in range(4):
            slot = holder.find(f"Slot{i}")
            if slot is None:
                continue
            if "Decay" in slot.attrib and "Mix" in slot.attrib and "reverb" not in out:
                slot.set("Mix", f"{rev:.0f}")
                slot.set("Bypass", "0" if rev > 1 else "1")
                out["reverb"] = f"{holder_tag}.Slot{i} @ {rev:.0f}%"
            elif "Delay" in slot.attrib and "Feedback" in slot.attrib and "delay" not in out:
                slot.set("Level", f"{dly:.0f}")
                slot.set("Bypass", "0" if dly > 1 else "1")
                out["delay"] = f"{holder_tag}.Slot{i} @ {dly:.0f}%"
    return out


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def export(preset_name: str, out_path: Path, template: Path | None, preset_dir: Path,
           amp_guid: str | None) -> dict:
    doc = load_preset(preset_name)
    tone = doc["config"]
    files = at5p_files(preset_dir)
    template = template or pick_template(files)
    pool = guid_pool(files)

    tree = ET.parse(template)
    root = tree.getroot()
    root.set("GUID", str(uuid.uuid4()))

    if amp_guid:
        if amp_guid not in pool:
            raise SystemExit(f"amp GUID {amp_guid} is not used by any preset in {preset_dir} "
                             "- refusing to write a model this install may not own")
        for tag in ("AmpA", "AmpB", "AmpC"):
            holder = root.find(tag)
            if holder is not None:
                holder.set("Model", amp_guid)

    names = None
    if amp_guid:
        names = params_for_model(files, amp_guid)
        if names is None:
            raise SystemExit(f"no preset in {preset_dir} uses amp {amp_guid}, so its parameter "
                             "names cannot be derived - pass --template with that amp instead")
    written = apply_amp(root, tone, names)
    eq_slot = apply_eq(root, tone)
    gate = apply_gate(root, tone)
    space = apply_space(root, tone)

    # every model GUID in the output must come from the user's own library
    for el in root.iter():
        for key, value in el.attrib.items():
            if len(value) == 36 and (key.startswith("Stomp") or key in ("Model", "CabModel")):
                if value not in pool and value != EMPTY_GUID:
                    raise SystemExit(f"refusing to write unknown model GUID {value} ({key})")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(out_path, encoding="UTF-8", xml_declaration=True)
    ET.parse(out_path)  # must reload as valid XML

    return {
        "preset": doc.get("name", preset_name),
        "template": str(template),
        "out": str(out_path),
        "size_bytes": out_path.stat().st_size,
        "amp_params": written,
        "eq_slot": eq_slot,
        "gate_written": gate,
        "space": space,
        "note": "AmpliTube lists the file after its next start (the browser reads Presets.db).",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preset", required=True, help="ToneForge preset slug or display name")
    ap.add_argument("--out", help="output .at5p path (default: <preset dir>/<name>.at5p)")
    ap.add_argument("--template", help=".at5p to clone (default: best of the local library)")
    ap.add_argument("--preset-dir", default=str(DEFAULT_PRESET_DIR), help="AmpliTube preset folder")
    ap.add_argument("--amp-guid", help="amp model GUID to use (must already be used by a local preset)")
    ap.add_argument("--json", action="store_true", help="print the result as JSON")
    args = ap.parse_args(argv)

    preset_dir = Path(args.preset_dir)
    doc = load_preset(args.preset)
    out = Path(args.out) if args.out else preset_dir / f"{doc.get('name', args.preset)}.at5p"
    result = export(args.preset, out, Path(args.template) if args.template else None,
                    preset_dir, args.amp_guid)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"wrote {result['out']} ({result['size_bytes']} bytes)")
        for key in ("eq_slot", "gate_written", "space", "amp_params"):
            print(f"  {key}: {result[key]}")
        print(f"  {result['note']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
