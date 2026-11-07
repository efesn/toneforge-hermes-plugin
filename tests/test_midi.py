"""MIDI bridge behaviour with mocked hardware. No device or AmpliTube needed."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from _pkg import midi_io


class FakeBackend:
    """Stands in for winmm/rtmidi and records every message."""

    name = "fake"

    def __init__(self, ports=None, *, fail=False):
        self.ports = ports if ports is not None else [
            {"index": 0, "name": "ToneForge", "backend": "fake", "technology": "virtual",
             "voices": 0, "is_synthesizer": False},
            {"index": 1, "name": "Microsoft GS Wavetable Synth", "backend": "fake",
             "technology": "synthesizer", "voices": 32, "is_synthesizer": True},
        ]
        self.sent: list[tuple] = []
        self.fail = fail
        self.closed = False

    def list_ports(self):
        return [dict(port) for port in self.ports]

    def send(self, port, status, data1, data2):
        if self.fail:
            raise midi_io.MidiSendError("device disappeared")
        self.sent.append((port["index"], status, data1, data2))

    def close(self):
        self.closed = True


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.backend = FakeBackend()
        self.service = midi_io.MidiService(
            root=self.root, backend_override=self.backend, sleep=lambda _: None
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_ports_flags_loopbacks(self):
        listed = self.service.list_ports()
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["count"], 2)
        self.assertTrue(listed["ports"][0]["looks_like_loopback"])
        self.assertFalse(listed["ports"][1]["looks_like_loopback"])

    def test_select_by_name_is_case_insensitive(self):
        result = self.service.select_port(port="toneforge")
        self.assertEqual(result["selected"]["index"], 0)
        self.assertEqual(self.service.read_config()["port"]["name"], "ToneForge")

    def test_select_by_index(self):
        result = self.service.select_port(port=1)
        self.assertEqual(result["selected"]["name"], "Microsoft GS Wavetable Synth")

    def test_select_unknown_port_lists_alternatives(self):
        with self.assertRaises(midi_io.MidiPortError) as ctx:
            self.service.select_port(port="does-not-exist")
        self.assertIn("ToneForge", str(ctx.exception))

    def test_select_ambiguous_partial_is_refused(self):
        backend = FakeBackend(ports=[
            {"index": 0, "name": "Guitar Rig Loop", "backend": "fake", "technology": "virtual",
             "voices": 0, "is_synthesizer": False},
            {"index": 1, "name": "Guitar Rig Loop 2", "backend": "fake", "technology": "virtual",
             "voices": 0, "is_synthesizer": False},
        ])
        service = midi_io.MidiService(root=self.root, backend_override=backend)
        with self.assertRaises(midi_io.MidiPortError) as ctx:
            service.select_port(port="guitar rig")
        self.assertIn("ambiguous", str(ctx.exception))

    def test_select_without_a_port_name_is_refused(self):
        with self.assertRaises(midi_io.MidiPortError):
            self.service.select_port(port=None)

    def test_sending_without_a_selection_is_refused(self):
        with self.assertRaises(midi_io.MidiPortError) as ctx:
            self.service.send_cc(channel=1, cc=20, value=64)
        self.assertIn("never sends", str(ctx.exception))
        self.assertEqual(self.backend.sent, [])

    def test_send_writes_a_control_change_message(self):
        self.service.select_port(port="ToneForge")
        result = self.service.send_cc(channel=1, cc=20, value=80)
        self.assertTrue(result["sent"])
        self.assertEqual(result["applied"], "unverified")
        self.assertEqual(result["bytes_hex"], "B0 14 50")
        self.assertEqual(self.backend.sent, [(0, 0xB0, 20, 80)])

    def test_channel_is_encoded_in_the_status_byte(self):
        self.service.select_port(port="ToneForge")
        self.service.send_cc(channel=16, cc=7, value=1)
        self.assertEqual(self.backend.sent[-1], (0, 0xBF, 7, 1))

    def test_invalid_midi_values_are_refused(self):
        self.service.select_port(port="ToneForge")
        for kwargs in (
            {"channel": 0, "cc": 1, "value": 1},
            {"channel": 17, "cc": 1, "value": 1},
            {"channel": 1, "cc": 128, "value": 1},
            {"channel": 1, "cc": 1, "value": 128},
            {"channel": 1, "cc": 1, "value": -1},
        ):
            with self.assertRaises(Exception, msg=str(kwargs)):
                self.service.send_cc(**kwargs)
        self.assertEqual(self.backend.sent, [])

    def test_selection_persists_across_instances(self):
        self.service.select_port(port="ToneForge")
        second = midi_io.MidiService(root=self.root, backend_override=FakeBackend())
        self.assertEqual(second.read_config()["port"]["name"], "ToneForge")

    def test_missing_selected_port_does_not_fall_back(self):
        self.service.select_port(port="ToneForge")
        self.backend.ports = [port for port in self.backend.ports if port["name"] != "ToneForge"]
        with self.assertRaises(midi_io.MidiPortError) as ctx:
            self.service.send_cc(channel=1, cc=20, value=1)
        self.assertIn("no longer available", str(ctx.exception))
        self.assertEqual(self.backend.sent, [])

    def test_backend_failure_surfaces_as_send_error(self):
        self.service.select_port(port="ToneForge")
        self.backend.fail = True
        with self.assertRaises(midi_io.MidiSendError):
            self.service.send_cc(channel=1, cc=20, value=1)

    def test_probe_sends_the_requested_sequence(self):
        self.service.select_port(port="ToneForge")
        result = self.service.probe(channel=1, cc=20, values=(0, 127, 64))
        self.assertEqual(result["values"], [0, 127, 64])
        self.assertEqual([entry[3] for entry in self.backend.sent], [0, 127, 64])

    def test_one_off_port_argument_does_not_change_the_selection(self):
        self.service.send_cc(channel=1, cc=20, value=5, port="Microsoft GS Wavetable")
        self.assertEqual(self.backend.sent[-1][0], 1)
        self.assertIsNone(self.service.read_config()["port"])

    def test_clear_selection(self):
        self.service.select_port(port="ToneForge")
        self.service.clear_selection()
        self.assertIsNone(self.service.read_config()["port"])

    def test_no_ports_at_all_is_a_clear_error(self):
        backend = FakeBackend(ports=[])
        service = midi_io.MidiService(root=self.root, backend_override=backend)
        with self.assertRaises(midi_io.MidiPortError) as ctx:
            service.select_port(port=0)
        self.assertIn("loopMIDI", str(ctx.exception))


class BackendSelectionTests(unittest.TestCase):
    def test_unknown_backend_preference_is_refused(self):
        with self.assertRaises(Exception):
            midi_io.default_backend("alsa")

    def test_auto_returns_a_backend_or_none(self):
        backend = midi_io.default_backend("auto")
        if backend is not None:
            self.assertIn(backend.name, midi_io.SUPPORTED_BACKENDS)

    def test_error_code_description(self):
        self.assertIn("device already allocated", midi_io.describe_error_code(4))
        self.assertIn("no MIDI device", midi_io.describe_error_code(68))
        self.assertIn("999", midi_io.describe_error_code(999))


class WinMMTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "winmm only exists on Windows")
    def test_winmm_is_available_and_enumerates(self):
        self.assertTrue(midi_io.WinMMBackend.available())
        ports = midi_io.WinMMBackend().list_ports()
        self.assertIsInstance(ports, list)
        for port in ports:
            self.assertIn("index", port)
            self.assertIn("name", port)
            self.assertEqual(port["backend"], midi_io.BACKEND_WINMM)
            self.assertTrue(port["name"])

    @unittest.skipUnless(sys.platform == "win32", "winmm only exists on Windows")
    def test_invalid_device_index_fails_cleanly(self):
        backend = midi_io.WinMMBackend()
        backend._handles.clear()
        with self.assertRaises(midi_io.MidiPortError):
            backend._open(99)


if __name__ == "__main__":
    unittest.main()
