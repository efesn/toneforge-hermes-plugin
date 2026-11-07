"""Live smoke test: drive the installed plugin's tools against the real winmm MIDI driver.

Not part of the unit suite (it needs a real Windows MIDI stack); run manually:
    python3 scripts/live_midi_check.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

import importlib.util

spec = importlib.util.spec_from_file_location(
    "toneforge_live", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
)
module = importlib.util.module_from_spec(spec)
sys.modules["toneforge_live"] = module
spec.loader.exec_module(module)

from toneforge_live import midi_io, tools  # noqa: E402


def show(title, payload):
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, ensure_ascii=False)[:1600])


def main() -> int:
    tmp = tempfile.TemporaryDirectory()
    os.environ["TONEFORGE_DATA_DIR"] = tmp.name
    tools.configure(midi_backend="winmm", default_channel=1)

    status = json.loads(tools.midi_status({}))
    show("midi_status", status)

    ports = json.loads(tools.list_midi_ports({}))
    show("list_midi_ports", ports)
    if not ports.get("ports"):
        print("\nNo MIDI output ports on this machine - skipping the send test.")
        return 0

    first = ports["ports"][0]
    print(f"\nSelecting port {first['index']}: {first['name']}")
    show("select_midi_port", json.loads(tools.select_midi_port({"port": first["index"]})))

    show("map_parameter", json.loads(tools.map_parameter({"parameter": "amp_gain", "cc": 20})))

    sent = json.loads(tools.set_parameter({"parameter": "gain", "value": 80}))
    show("set_parameter -> real MIDI out", sent)
    ok = bool(sent.get("ok") and sent.get("sent"))
    print("\nLIVE MIDI SEND:", "OK" if ok else "FAILED")

    probe = json.loads(tools.midi_probe({"cc": 20, "values": [0, 127, 64]}))
    show("midi_probe", probe)

    missing = json.loads(tools.send_midi({"cc": 20, "value": 1}))
    print("\n(selection is active; this call is expected to succeed via the selected port:", missing.get("ok"), ")")

    tools._service.clear_selection()
    blocked = json.loads(tools.send_midi({"cc": 20, "value": 1}))
    print("\nafter clearing the selection, send_midi returns ok =", blocked.get("ok"))
    print("error:", blocked.get("error", "")[:160])

    tools._service = None
    midi_io.WinMMBackend().close()
    tmp.cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
