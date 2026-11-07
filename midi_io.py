"""MIDI output bridge for AmpliTube 5 Standalone on Windows.

Why two backends
----------------
``python-rtmidi`` is the best-known Python MIDI library, but it has no wheel for
every CPython release (it needs a C++ toolchain when a wheel is missing). A
guitar-tone plugin that only works when a compiler is installed is not a good
plugin, so ToneForge speaks to the Windows MIDI Mapper directly through
``winmm.dll`` using :mod:`ctypes` - standard library only, no build step, works
on any Windows Python. ``python-rtmidi`` is used when it *is* importable
(``auto`` prefers it), and on non-Windows platforms it is the only backend.

What this module will not do
----------------------------
* It never picks a port on its own. Sending requires an explicit selection
  (persisted in ``midi_config.json``) or an explicit ``port`` argument.
* It never claims a message was *applied*. A zero return code means Windows
  accepted the bytes for delivery; whether AmpliTube's assigned parameter moved
  is only knowable by watching AmpliTube.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import validation as V

BACKEND_WINMM = "winmm"
BACKEND_RTMIDI = "rtmidi"
SUPPORTED_BACKENDS = (BACKEND_WINMM, BACKEND_RTMIDI)

MMSYSERR_NAMES = {
    0: "no error",
    1: "unspecified error",
    2: "invalid device id",
    3: "driver not enabled",
    4: "device already allocated by another application",
    5: "invalid handle",
    6: "no device driver present",
    7: "out of memory",
    8: "operation not supported",
    9: "bad error number",
    10: "invalid flag",
    11: "invalid parameter",
    12: "handle busy",
    13: "invalid alias",
    14: "bad database",
    15: "key not found",
    16: "read error",
    17: "write error",
    18: "delete error",
    19: "value not found",
    20: "internal error",
}
MIDIERR_NAMES = {
    64: "MIDI data not prepared",
    65: "still playing",
    66: "no mapping",
    67: "not ready",
    68: "no MIDI device",
    69: "invalid MIDI setup",
    70: "bad open mode",
    71: "device does not continue",
}
TECHNOLOGY_NAMES = {
    1: "MIDI port",
    2: "synthesizer",
    3: "square-wave synthesizer",
    4: "FM synthesizer",
    5: "MIDI mapper",
    6: "wavetable synthesizer",
    7: "software synthesizer",
}
SYNTH_TECHNOLOGIES = {2, 3, 4, 6, 7}


class MidiError(V.ToneForgeError):
    """Base class for MIDI failures."""


class MidiUnavailable(MidiError):
    """No usable MIDI backend on this machine."""


class MidiPortError(MidiError):
    """The requested port does not exist, or none was selected."""


class MidiSendError(MidiError):
    """The backend refused the message."""


def describe_error_code(code: int) -> str:
    if code in MMSYSERR_NAMES:
        return f"MMSYSERR {code}: {MMSYSERR_NAMES[code]}"
    if code in MIDIERR_NAMES:
        return f"MIDIERR {code}: {MIDIERR_NAMES[code]}"
    return f"error code {code}"


# --------------------------------------------------------------------------- #
# winmm backend (stdlib only)
# --------------------------------------------------------------------------- #
class _MIDIOUTCAPS(ctypes.Structure):
    _fields_ = [
        ("wMid", ctypes.c_ushort),
        ("wPid", ctypes.c_ushort),
        ("vDriverVersion", ctypes.c_uint),
        ("szPname", ctypes.c_wchar * 32),
        ("wTechnology", ctypes.c_ushort),
        ("wVoices", ctypes.c_ushort),
        ("wNotes", ctypes.c_ushort),
        ("wChannelMask", ctypes.c_ushort),
        ("dwSupport", ctypes.c_uint),
    ]


_winmm_lock = threading.Lock()
_winmm_lib: Any = None
_winmm_error: Optional[str] = None


def _winmm() -> Any:
    """Load and configure winmm once. Returns None when unavailable."""
    global _winmm_lib, _winmm_error
    if _winmm_lib is not None or _winmm_error is not None:
        return _winmm_lib
    with _winmm_lock:
        if _winmm_lib is not None or _winmm_error is not None:
            return _winmm_lib
        if sys.platform != "win32":
            _winmm_error = "the winmm backend only exists on Windows"
            return None
        try:
            lib = ctypes.WinDLL("winmm")  # type: ignore[attr-defined]
            lib.midiOutGetNumDevs.restype = ctypes.c_uint
            lib.midiOutGetDevCapsW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_MIDIOUTCAPS), ctypes.c_uint]
            lib.midiOutGetDevCapsW.restype = ctypes.c_uint
            lib.midiOutOpen.argtypes = [
                ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint,
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
            ]
            lib.midiOutOpen.restype = ctypes.c_uint
            lib.midiOutClose.argtypes = [ctypes.c_void_p]
            lib.midiOutClose.restype = ctypes.c_uint
            lib.midiOutReset.argtypes = [ctypes.c_void_p]
            lib.midiOutReset.restype = ctypes.c_uint
            lib.midiOutShortMsg.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            lib.midiOutShortMsg.restype = ctypes.c_uint
            _winmm_lib = lib
        except OSError as exc:  # pragma: no cover - only on a broken Windows install
            _winmm_error = f"winmm.dll could not be loaded: {exc}"
            _winmm_lib = None
    return _winmm_lib


class WinMMBackend:
    """Windows MIDI output through ``winmm.dll``."""

    name = BACKEND_WINMM

    def __init__(self) -> None:
        self._handles: dict[int, Any] = {}
        self._lock = threading.Lock()

    # -- discovery --------------------------------------------------------- #
    @staticmethod
    def available() -> bool:
        return _winmm() is not None

    @staticmethod
    def unavailable_reason() -> str:
        return _winmm_error or "winmm is available"

    def list_ports(self) -> list[dict[str, Any]]:
        lib = _winmm()
        if lib is None:
            raise MidiUnavailable(self.unavailable_reason())
        ports: list[dict[str, Any]] = []
        for index in range(int(lib.midiOutGetNumDevs())):
            caps = _MIDIOUTCAPS()
            code = lib.midiOutGetDevCapsW(ctypes.c_void_p(index), ctypes.byref(caps), ctypes.sizeof(caps))
            if code != 0:
                continue
            ports.append(
                {
                    "index": index,
                    "name": _clean_name(caps.szPname),
                    "backend": self.name,
                    "technology": TECHNOLOGY_NAMES.get(caps.wTechnology, f"unknown ({caps.wTechnology})"),
                    "voices": int(caps.wVoices),
                    "is_synthesizer": caps.wTechnology in SYNTH_TECHNOLOGIES,
                }
            )
        return ports

    # -- sending ----------------------------------------------------------- #
    def send(self, port: dict[str, Any], status: int, data1: int, data2: int) -> None:
        lib = _winmm()
        if lib is None:
            raise MidiUnavailable(self.unavailable_reason())
        index = int(port["index"])
        with self._lock:
            handle = self._open(index)
            message = (status & 0xFF) | ((data1 & 0x7F) << 8) | ((data2 & 0x7F) << 16)
            code = int(lib.midiOutShortMsg(handle, ctypes.c_uint(message)))
            if code != 0:
                # A stale handle is the common case after a device change: drop it.
                self._close_locked(index)
                raise MidiSendError(
                    f"Windows rejected the MIDI message to port {index}: {describe_error_code(code)}"
                )

    def _open(self, index: int) -> Any:
        handle = self._handles.get(index)
        if handle is not None:
            return handle
        lib = _winmm()
        assert lib is not None
        raw = ctypes.c_void_p()
        code = int(lib.midiOutOpen(ctypes.byref(raw), ctypes.c_uint(index), None, None, 0))
        if code != 0:
            raise MidiPortError(
                f"cannot open MIDI output port {index}: {describe_error_code(code)}. "
                "Close the application holding it (or restart loopMIDI) and try again."
            )
        self._handles[index] = raw
        return raw

    def _close_locked(self, index: int) -> None:
        handle = self._handles.pop(index, None)
        if handle is None:
            return
        lib = _winmm()
        if lib is not None:
            lib.midiOutReset(handle)
            lib.midiOutClose(handle)

    def close(self) -> None:
        with self._lock:
            for index in list(self._handles):
                self._close_locked(index)


def _clean_name(raw: Any) -> str:
    name = str(raw or "").strip()
    name = name.split("\x00")[0].strip()
    return name or "(unnamed MIDI port)"


# --------------------------------------------------------------------------- #
# python-rtmidi backend (optional)
# --------------------------------------------------------------------------- #
class RtMidiBackend:
    """MIDI output through ``python-rtmidi`` when it is installed."""

    name = BACKEND_RTMIDI

    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _module() -> Any:
        try:
            import rtmidi  # type: ignore
        except Exception:
            return None
        return rtmidi

    @classmethod
    def available(cls) -> bool:
        return cls._module() is not None

    @staticmethod
    def unavailable_reason() -> str:
        return "python-rtmidi is not installed in this Python environment"

    def list_ports(self) -> list[dict[str, Any]]:
        rtmidi = self._module()
        if rtmidi is None:
            raise MidiUnavailable(self.unavailable_reason())
        probe = rtmidi.MidiOut()
        try:
            names = list(probe.get_ports())
        finally:
            close = getattr(probe, "close_port", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            delete = getattr(probe, "delete", None)
            if callable(delete):
                try:
                    delete()
                except Exception:
                    pass
        return [
            {"index": index, "name": str(name), "backend": self.name, "technology": "rtmidi", "voices": 0,
             "is_synthesizer": False}
            for index, name in enumerate(names)
        ]

    def send(self, port: dict[str, Any], status: int, data1: int, data2: int) -> None:
        rtmidi = self._module()
        if rtmidi is None:
            raise MidiUnavailable(self.unavailable_reason())
        name = str(port["name"])
        with self._lock:
            out = self._ports.get(name)
            if out is None:
                out = rtmidi.MidiOut()
                available = list(out.get_ports())
                if name not in available:
                    delete = getattr(out, "delete", None)
                    if callable(delete):
                        delete()
                    raise MidiPortError(
                        f"rtmidi port {name!r} is no longer present "
                        f"(available: {', '.join(available) or 'none'})"
                    )
                out.open_port(available.index(name), name)
                self._ports[name] = out
            try:
                out.send_message([status & 0xFF, data1 & 0x7F, data2 & 0x7F])
            except Exception as exc:
                self._ports.pop(name, None)
                raise MidiSendError(f"rtmidi refused the message to {name!r}: {exc}") from None

    def close(self) -> None:
        with self._lock:
            for name, out in list(self._ports.items()):
                try:
                    out.close_port()
                except Exception:
                    pass
                self._ports.pop(name, None)


# --------------------------------------------------------------------------- #
# Service
# --------------------------------------------------------------------------- #
def default_backend(preference: str = "auto") -> Optional[Any]:
    """Return a backend instance for *preference* (or None when unavailable)."""
    preference = (preference or "auto").strip().lower()
    if preference not in ("auto",) + SUPPORTED_BACKENDS:
        raise V.ValidationError(
            f"midi backend must be one of: auto, {', '.join(SUPPORTED_BACKENDS)}"
        )
    order = (BACKEND_RTMIDI, BACKEND_WINMM) if preference == "auto" else (preference,)
    factories = {BACKEND_RTMIDI: RtMidiBackend, BACKEND_WINMM: WinMMBackend}
    for name in order:
        factory = factories[name]
        if factory.available():
            return factory()
    return None


class MidiService:
    """Port selection, status and CC sending on top of a backend."""

    CONFIG_NAME = "midi_config.json"

    def __init__(
        self,
        *,
        backend_preference: str = "auto",
        root: Optional[Path] = None,
        backend_override: Optional[Any] = None,
        default_channel: int = 1,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        from . import preset_store

        self.root = Path(root) if root is not None else preset_store.data_dir()
        self.backend_preference = backend_preference
        self.default_channel = default_channel
        self._sleep = sleep
        self._override = backend_override
        self._backend: Optional[Any] = None
        self._backend_error: Optional[str] = None
        self._lock = threading.Lock()

    # -- config file ------------------------------------------------------- #
    @property
    def config_path(self) -> Path:
        return self.root / self.CONFIG_NAME

    def read_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {"backend": "auto", "port": None, "channel": self.default_channel}
        try:
            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise MidiError(f"midi_config.json is not readable: {exc}") from None
        if not isinstance(data, dict):
            raise MidiError("midi_config.json does not contain a JSON object")
        data.setdefault("backend", "auto")
        data.setdefault("port", None)
        data.setdefault("channel", self.default_channel)
        return data

    def write_config(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False)
        handle = None
        temp_name = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=".midi_config.", suffix=".tmp", dir=str(self.root))
            handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            handle = None
            os.replace(temp_name, self.config_path)
            temp_name = None
        finally:
            if handle is not None:
                handle.close()
            if temp_name is not None and os.path.exists(temp_name):
                os.unlink(temp_name)

    # -- backend ----------------------------------------------------------- #
    def backend(self) -> Optional[Any]:
        with self._lock:
            if self._override is not None:
                return self._override
            if self._backend is not None:
                return self._backend
            try:
                self._backend = default_backend(self.backend_preference)
            except V.ValidationError as exc:
                self._backend_error = str(exc)
                self._backend = None
            if self._backend is None:
                self._backend_error = self._backend_error or (
                    "no MIDI backend is available: install python-rtmidi or run on Windows"
                )
            return self._backend

    def backend_name(self) -> Optional[str]:
        backend = self.backend()
        return getattr(backend, "name", None) if backend is not None else None

    def close(self) -> None:
        backend = self.backend()
        closer = getattr(backend, "close", None)
        if callable(closer):
            closer()

    # -- discovery --------------------------------------------------------- #
    def list_ports(self) -> dict[str, Any]:
        backend = self.backend()
        if backend is None:
            return {
                "ok": False,
                "backend": None,
                "ports": [],
                "error": self._backend_error,
                "hint": (
                    "On Windows the built-in winmm backend needs no dependency. If this is not Windows, "
                    "install python-rtmidi (it must have a wheel for your Python version)."
                ),
            }
        ports = backend.list_ports()
        for port in ports:
            port["selection"] = _selection_for(port)
            port["looks_like_loopback"] = _looks_like_loopback(port["name"])
        return {
            "ok": True,
            "backend": getattr(backend, "name", "unknown"),
            "count": len(ports),
            "ports": ports,
            "selected": self.read_config().get("port"),
            "hint": (
                "Choose a virtual loopback port (loopMIDI) that AmpliTube also has selected as its MIDI input. "
                "ToneForge will not pick one for you."
            ),
        }

    # -- selection --------------------------------------------------------- #
    def select_port(self, *, port: Any = None, backend: Optional[str] = None) -> dict[str, Any]:
        ports = self.list_ports()
        if not ports.get("ok"):
            raise MidiUnavailable(ports.get("error") or "no MIDI backend available")
        available = ports["ports"]
        if not available:
            raise MidiPortError(
                "no MIDI output ports exist. Create one with loopMIDI (e.g. 'ToneForge'), "
                "then restart AmpliTube so it sees the new port."
            )
        chosen = self._match_port(available, port, backend)
        config = self.read_config()
        config["port"] = _selection_for(chosen)
        config["backend"] = backend or self.backend_preference
        self.write_config(config)
        return {"ok": True, "selected": config["port"], "available": [p["name"] for p in available]}

    def clear_selection(self) -> dict[str, Any]:
        config = self.read_config()
        config["port"] = None
        self.write_config(config)
        return {"ok": True, "selected": None}

    def selected_port(self) -> dict[str, Any]:
        config = self.read_config()
        selection = config.get("port")
        if not selection:
            raise MidiPortError(
                "no MIDI output port is selected. Run toneforge_list_midi_ports, then "
                "toneforge_select_midi_port. ToneForge never sends to a port you did not choose."
            )
        return selection

    def _match_port(self, available: list[dict[str, Any]], port: Any, backend: Optional[str]) -> dict[str, Any]:
        candidates = [p for p in available if not backend or p["backend"] == backend] or available
        if port is None:
            raise MidiPortError(
                "name the port to select: pass an index (0, 1, ...) or a port name such as 'ToneForge'"
            )
        if isinstance(port, bool):
            raise V.ValidationError("port must be an index or a name")
        if isinstance(port, int) or (isinstance(port, str) and port.strip().isdigit()):
            index = int(port)
            for candidate in candidates:
                if candidate["index"] == index:
                    return candidate
            raise MidiPortError(
                f"no MIDI output port with index {index}; available: "
                + ", ".join(f"{p['index']}={p['name']}" for p in candidates)
            )
        if isinstance(port, str):
            needle = port.strip().casefold()
            exact = [p for p in candidates if p["name"].casefold() == needle]
            if len(exact) == 1:
                return exact[0]
            partial = [p for p in candidates if needle in p["name"].casefold()]
            if len(partial) == 1:
                return partial[0]
            if len(partial) > 1:
                raise MidiPortError(
                    f"{port!r} is ambiguous: "
                    + ", ".join(f"{p['index']}={p['name']}" for p in partial)
                )
            raise MidiPortError(
                f"no MIDI output port matching {port!r}; available: "
                + ", ".join(p["name"] for p in candidates)
            )
        raise V.ValidationError("port must be an index or a name")

    def _resolve_send_port(self, port: Any, backend: Optional[str]) -> dict[str, Any]:
        if port is None:
            selection = self.selected_port()
            listed = self.list_ports()
            if not listed.get("ok"):
                raise MidiUnavailable(listed.get("error") or "no MIDI backend available")
            for candidate in listed["ports"]:
                if (
                    candidate["name"] == selection.get("name")
                    and candidate["index"] == selection.get("index")
                    and candidate["backend"] == selection.get("backend")
                ):
                    return candidate
            # The saved port vanished: never fall back to another one silently.
            raise MidiPortError(
                f"the selected port {selection.get('name')!r} is no longer available. "
                "Run toneforge_list_midi_ports and select again."
            )
        listed = self.list_ports()
        if not listed.get("ok"):
            raise MidiUnavailable(listed.get("error") or "no MIDI backend available")
        return self._match_port(listed["ports"], port, backend)

    # -- sending ----------------------------------------------------------- #
    def send_cc(
        self,
        *,
        channel: int,
        cc: int,
        value: int,
        port: Any = None,
        backend: Optional[str] = None,
    ) -> dict[str, Any]:
        channel = int(V.coerce_int(channel, "channel", lo=1, hi=16))
        cc = int(V.coerce_int(cc, "cc", lo=0, hi=127))
        value = int(V.coerce_int(value, "value", lo=0, hi=127))
        backend_obj = self.backend()
        if backend_obj is None:
            raise MidiUnavailable(self._backend_error or "no MIDI backend available")

        target = self._resolve_send_port(port, backend)
        status = 0xB0 | (channel - 1)
        backend_obj.send(target, status, cc, value)
        return {
            "ok": True,
            "sent": True,
            "applied": "unverified",
            "backend": target.get("backend"),
            "port": {"index": target["index"], "name": target["name"]},
            "channel": channel,
            "cc": cc,
            "value": value,
            "bytes_hex": f"{status:02X} {cc:02X} {value:02X}",
            "note": (
                "Windows accepted the bytes for delivery. This does NOT prove AmpliTube received them "
                "or that the assigned parameter moved - watch AmpliTube to confirm."
            ),
        }

    def probe(
        self,
        *,
        channel: int,
        cc: int,
        port: Any = None,
        backend: Optional[str] = None,
        values: tuple[int, ...] = (0, 127, 64),
        gap_s: float = 0.25,
    ) -> dict[str, Any]:
        """Send a short value sequence, e.g. to bind a CC during MIDI Learn."""
        sent: list[int] = []
        for index, value in enumerate(values):
            self.send_cc(channel=channel, cc=cc, value=value, port=port, backend=backend)
            sent.append(value)
            if index < len(values) - 1 and gap_s > 0:
                self._sleep(gap_s)
        return {
            "ok": True,
            "sent": True,
            "applied": "unverified",
            "channel": channel,
            "cc": cc,
            "values": sent,
            "note": (
                "Sequence sent. If AmpliTube was in 'Learn' mode, it should now be bound to this CC; "
                "the final value leaves the parameter at "
                f"{sent[-1]}/127."
            ),
        }


def _selection_for(port: dict[str, Any]) -> dict[str, Any]:
    return {"backend": port["backend"], "index": port["index"], "name": port["name"]}


def _looks_like_loopback(name: str) -> bool:
    folded = name.casefold()
    return any(
        token in folded
        for token in ("loop", "virtual", "toneforge", "midi through", "internal", "iac")
    )
