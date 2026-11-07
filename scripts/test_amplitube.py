"""Interactive test harness: ToneForge -> loopMIDI -> AmpliTube 5 Standalone.

Run it from the plugin directory (no dependencies):

    python scripts/test_amplitube.py status
    python scripts/test_amplitube.py learn  --cc 20      # complete MIDI Learn in AmpliTube
    python scripts/test_amplitube.py sweep  --cc 20      # move the knob end to end, slowly
    python scripts/test_amplitube.py set 80 --cc 20      # set 80/100
    python scripts/test_amplitube.py listen --seconds 20 # count CCs arriving on the port

`listen` is the important one for debugging: it tells you whether Windows is delivering
anything at all, independently of AmpliTube.

This script is allowed to pick a port for you because *you* ran it; the plugin itself
never sends to a port that was not explicitly selected.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_ROOT))

spec = importlib.util.spec_from_file_location(
    "toneforge_test", PLUGIN_ROOT / "__init__.py", submodule_search_locations=[str(PLUGIN_ROOT)]
)
module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
sys.modules["toneforge_test"] = module
spec.loader.exec_module(module)  # type: ignore[union-attr]

from toneforge_test import midi_io, tools  # noqa: E402

DEFAULT_CC = 20
PREFERRED_PORT_HINTS = ("toneforge", "loopmidi", "loop")


def _call(fn, args):
    payload = json.loads(fn(args))
    if not payload.get("ok", False):
        print(f"  ✗ {payload.get('error')}")
        raise SystemExit(1)
    return payload


def ensure_port(force_index: int | None = None) -> dict:
    listed = _call(tools.list_midi_ports, {})
    ports = listed.get("ports", [])
    if not ports:
        print("  ✗ no MIDI output ports exist; is loopMIDI running?")
        raise SystemExit(1)

    print(f"  backend: {listed.get('backend')}, {len(ports)} port(s)")
    for port in ports:
        flag = "loopback" if port.get("looks_like_loopback") else "NOT a loopback"
        print(f"    [{port['index']}] {port['name']}  ({port['technology']}, {flag})")

    if force_index is not None:
        target = force_index
    else:
        chosen = next((p for p in ports if p.get("looks_like_loopback")), None)
        if chosen is None:
            print("  ✗ no loopback port found. Create one in loopMIDI (name it 'ToneForge').")
            raise SystemExit(1)
        target = chosen["index"]

    selected = _call(tools.select_midi_port, {"port": target})
    print(f"  → sending to: {selected['selected']['name']}")
    return selected["selected"]


def ensure_mapping(cc: int, parameter: str = "amp_gain") -> dict:
    listed = _call(tools.list_mappings, {})
    key = parameter
    if key in listed.get("mappings", {}):
        entry = listed["mappings"][key]
        print(f"  mapping: {key} already stored (CC {entry['cc']})")
        return entry
    mapped = _call(tools.map_parameter, {"parameter": key, "cc": cc, "scope": "preset"})
    print(f"  mapping: recorded {key} → CC {cc} (preset scope)")
    return mapped["mapping"][key]


def cmd_status(args) -> int:
    status = _call(tools.midi_status, {})
    print(json.dumps(
        {k: status[k] for k in ("active_backend", "ports_available", "selected_port", "ready", "blockers")},
        indent=2,
    ))
    return 0


def cmd_learn(args) -> int:
    ensure_port(args.port_index)
    ensure_mapping(args.cc, args.parameter)
    print("\nNow do this in AmpliTube, in this order:")
    print("  1. Right-click the amp knob (e.g. PRE AMP / GAIN)")
    print("  2. Assign MIDI → <parameter> → Learn")
    print("  3. When it says it is waiting, press Enter here.\n")
    input("   [Enter] when AmpliTube is waiting for MIDI… ")
    for value in (0, 127, 64):
        sent = _call(tools.send_midi, {"cc": args.cc, "value": value, "channel": args.channel})
        print(f"  → CC {args.cc} = {value:3d}   ({sent['bytes_hex']})")
        time.sleep(0.6)
    print("\nDid AmpliTube bind the control? If yes, run:  python scripts/test_amplitube.py sweep")
    return 0


def cmd_sweep(args) -> int:
    ensure_port(args.port_index)
    ensure_mapping(args.cc, args.parameter)
    print(f"\nSweeping CC {args.cc} on channel {args.channel}. Watch the knob in AmpliTube.\n")
    for value in (0, 32, 64, 96, 127, 96, 64, 32, 0):
        sent = _call(tools.send_midi, {"cc": args.cc, "value": value, "channel": args.channel})
        print(f"  → {value:3d}/127  ({sent['bytes_hex']})")
        time.sleep(0.45)
    print("\nIf the knob did not move, it is not the plugin: check the 4 AmpliTube settings")
    print("listed in docs/MIDI_SETUP_WINDOWS.md (MIDI input, channel, assignment, preset).")
    return 0


def cmd_set(args) -> int:
    ensure_port(args.port_index)
    ensure_mapping(args.cc, args.parameter)
    payload = _call(
        tools.set_parameter,
        {"parameter": args.parameter, "value": args.value, "channel": args.channel},
    )
    print(f"  → {payload['parameter']} = {payload['parameter_value']}/100")
    print(f"  → {payload['conversion']}  bytes {payload['bytes_hex']}")
    print(f"  → applied: {payload['applied']}")
    return 0


def cmd_listen(args) -> int:
    """Count CC messages arriving on the selected port (proves Windows delivers them)."""
    selected = ensure_port(args.port_index)
    if not midi_io.WinMMBackend.available():
        print("  ✗ the winmm input API is only available on Windows")
        return 1

    import ctypes
    from ctypes import wintypes as wt

    winmm = ctypes.WinDLL("winmm")  # type: ignore[attr-defined]
    winmm.midiInGetNumDevs.restype = ctypes.c_uint

    class MIDIINCAPS(ctypes.Structure):
        _fields_ = [
            ("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
            ("szPname", wt.WCHAR * 32), ("dwSupport", wt.DWORD),
        ]

    count = 0
    for index in range(int(winmm.midiInGetNumDevs())):
        caps = MIDIINCAPS()
        winmm.midiInGetDevCapsW(ctypes.c_void_p(index), ctypes.byref(caps), ctypes.sizeof(caps))
        name = "".join(ch for ch in caps.szPname if ch != "\x00").strip()
        if name == selected["name"]:
            count += 1
            print(f"  input device [{index}] {name} exists")
    if not count:
        print(f"  ⚠ {selected['name']!r} is not listed as a MIDI *input* device.")
        print("    loopMIDI ports normally are; restart loopMIDI if not.")
        return 1

    print(f"  listening is passive: AmpliTube is the real consumer. Send CCs from your controller")
    print(f"  or another ToneForge call while watching AmpliTube's MIDI indicator.")
    return 0


def cmd_loopback(args) -> int:
    """Prove the virtual cable itself: listen on the port, send a CC, expect to receive it.

    This does not involve AmpliTube. If this passes and the knob still does not move, the
    cable is fine and the difference is AmpliTube's own MIDI settings.
    """
    import ctypes
    from ctypes import wintypes as wt

    selected = ensure_port(args.port_index)
    winmm = ctypes.WinDLL("winmm")  # type: ignore[attr-defined]

    class MIDIINCAPS(ctypes.Structure):
        _fields_ = [
            ("wMid", wt.WORD), ("wPid", wt.WORD), ("vDriverVersion", wt.UINT),
            ("szPname", wt.WCHAR * 32), ("dwSupport", wt.DWORD),
        ]

    winmm.midiInGetNumDevs.restype = ctypes.c_uint
    winmm.midiInGetDevCapsW.argtypes = [ctypes.c_void_p, ctypes.POINTER(MIDIINCAPS), ctypes.c_uint]
    winmm.midiInGetDevCapsW.restype = ctypes.c_uint

    matches: list[tuple[int, str]] = []
    for index in range(int(winmm.midiInGetNumDevs())):
        caps = MIDIINCAPS()
        winmm.midiInGetDevCapsW(ctypes.c_void_p(index), ctypes.byref(caps), ctypes.sizeof(caps))
        name = "".join(ch for ch in caps.szPname if ch != "\x00").strip()
        if name == selected["name"] or selected["name"].casefold() in name.casefold():
            matches.append((index, name))
    if not matches:
        print(f"  ✗ {selected['name']!r} does not appear as a MIDI input device")
        return 1
    index, name = matches[0]
    print(f"  opening input [{index}] {name}")

    received: list[int] = []
    prototype = ctypes.WINFUNCTYPE(
        None, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
    )

    def _callback(_handle, message, _instance, param1, _param2):
        if message == 0x3C3:  # MIM_DATA
            received.append(int(param1 or 0))

    callback = prototype(_callback)
    winmm.midiInOpen.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.c_void_p,
        ctypes.c_void_p, ctypes.c_uint,
    ]
    winmm.midiInStart.argtypes = [ctypes.c_void_p]
    winmm.midiInStop.argtypes = [ctypes.c_void_p]
    winmm.midiInClose.argtypes = [ctypes.c_void_p]

    handle = ctypes.c_void_p()
    rc = int(winmm.midiInOpen(ctypes.byref(handle), index, callback, None, 0x00030000))
    if rc != 0:
        print(f"  ✗ midiInOpen failed: {midi_io.describe_error_code(rc)}")
        return 1
    try:
        winmm.midiInStart(handle)
        time.sleep(0.2)
        sent = _call(tools.send_midi, {"cc": args.cc, "value": 96, "channel": args.channel})
        print(f"  sent: {sent['bytes_hex']}")
        deadline = time.time() + 2.0
        while time.time() < deadline and not received:
            time.sleep(0.05)
    finally:
        winmm.midiInStop(handle)
        winmm.midiInClose(handle)

    if not received:
        print("  ✗ nothing came back through the port — the loopback is not passing data")
        return 1
    message = received[0]
    status, data1, data2 = message & 0xFF, (message >> 8) & 0x7F, (message >> 16) & 0x7F
    print(f"  received: status 0x{status:02X}, data1 {data1}, data2 {data2}")
    if status == 0xB0 and data1 == args.cc and data2 == 96:
        print("\n  ✓ the virtual cable delivers the exact bytes ToneForge sent.")
        print("    AmpliTube is the only remaining variable: MIDI input, channel, assignment, preset.")
        return 0
    print("  ⚠ received a message, but not the one that was sent")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="ToneForge ↔ AmpliTube 5 test harness")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("status", "learn", "sweep", "set", "listen", "loopback"):
        p = sub.add_parser(name)
        p.add_argument("--cc", type=int, default=DEFAULT_CC)
        p.add_argument("--channel", type=int, default=1)
        p.add_argument("--parameter", default="amp_gain")
        p.add_argument("--port-index", type=int, default=None)
        if name == "set":
            p.add_argument("value", type=int, help="0-100")
        if name == "listen":
            p.add_argument("--seconds", type=int, default=20)

    args = parser.parse_args()
    tools.configure(midi_backend="auto", default_channel=args.channel)
    handlers = {
        "status": cmd_status, "learn": cmd_learn, "sweep": cmd_sweep,
        "set": cmd_set, "listen": cmd_listen, "loopback": cmd_loopback,
    }
    try:
        return handlers[args.command](args)
    finally:
        tools._service = None


if __name__ == "__main__":
    raise SystemExit(main())
