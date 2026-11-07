"""Tool handlers: the JSON contract the model actually sees, end to end."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from _pkg import midi_io, tools


class FakeBackend:
    name = "fake"

    def __init__(self):
        self.ports = [
            {"index": 0, "name": "ToneForge", "backend": "fake", "technology": "virtual",
             "voices": 0, "is_synthesizer": False},
        ]
        self.sent: list[tuple] = []

    def list_ports(self):
        return [dict(port) for port in self.ports]

    def send(self, port, status, data1, data2):
        self.sent.append((port["index"], status, data1, data2))

    def close(self):
        pass


class ToolContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._env = os.environ.get("TONEFORGE_DATA_DIR")
        os.environ["TONEFORGE_DATA_DIR"] = str(self.root)
        self.backend = FakeBackend()
        tools.configure(midi_backend="auto", default_channel=1)
        tools._service = midi_io.MidiService(
            root=self.root, backend_override=self.backend, sleep=lambda _: None
        )

    def tearDown(self):
        tools._service = None
        if self._env is None:
            os.environ.pop("TONEFORGE_DATA_DIR", None)
        else:
            os.environ["TONEFORGE_DATA_DIR"] = self._env
        self._tmp.cleanup()

    def call(self, fn, args=None):
        raw = fn(args or {})
        self.assertIsInstance(raw, str, "handlers must return a JSON string")
        payload = json.loads(raw)
        self.assertIsInstance(payload, dict)
        self.assertIn("ok", payload)
        return payload

    # -- tone design ------------------------------------------------------- #
    def test_create_returns_a_complete_recipe(self):
        payload = self.call(tools.create_preset, {"genre": "industrial metal", "tuning": "drop D"})
        self.assertTrue(payload["ok"])
        tone = payload["tone"]
        self.assertEqual(tone["genre"], "industrial_metal")
        self.assertEqual(tone["tuning"], "drop_d")
        self.assertFalse(payload["applies_automatically"])
        self.assertTrue(payload["how_to_apply"])
        self.assertTrue(tone["signal_chain"])
        self.assertTrue(tone["why"])

    def test_create_can_save_in_one_step(self):
        payload = self.call(
            tools.create_preset,
            {"genre": "thrash", "name": "Thrash Test", "save": True},
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["saved"]["slug"], "thrash-test")
        self.assertTrue((self.root / "presets" / "thrash-test.json").exists())

    def test_create_rejects_out_of_range_gain(self):
        payload = self.call(tools.create_preset, {"genre": "metal", "gain_level": 101})
        self.assertFalse(payload["ok"])
        self.assertIn("gain_level", payload["error"])

    def test_create_rejects_non_object_args(self):
        payload = json.loads(tools.create_preset("not a dict"))
        self.assertFalse(payload["ok"])
        self.assertIn("JSON object", payload["error"])

    def test_created_names_are_sanitised(self):
        payload = self.call(
            tools.create_preset, {"genre": "metal", "name": "../../escape", "save": True}
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["saved"]["slug"], "escape")
        self.assertTrue((self.root / "presets" / "escape.json").exists())
        self.assertFalse((self.root / "escape.json").exists())

    def test_list_profiles_covers_the_library(self):
        payload = self.call(tools.list_profiles)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["count"], 9)
        keys = {item["key"] for item in payload["profiles"]}
        self.assertIn("industrial_metal", keys)
        self.assertIn("ambient", keys)

    # -- library ----------------------------------------------------------- #
    def test_library_round_trip(self):
        created = self.call(tools.create_preset, {"genre": "hard rock", "name": "Rock A", "save": True})
        self.assertTrue(created["ok"])

        listed = self.call(tools.list_presets)
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["presets"][0]["slug"], "rock-a")

        fetched = self.call(tools.get_preset, {"preset": "rock-a"})
        self.assertTrue(fetched["ok"])
        self.assertEqual(fetched["preset"]["name"], "Rock A")
        self.assertEqual(fetched["tone"]["params"], created["tone"]["params"])

    def test_duplicate_save_is_refused_without_overwrite(self):
        self.call(tools.create_preset, {"genre": "metal", "name": "Dup", "save": True})
        again = self.call(tools.create_preset, {"genre": "metal", "name": "Dup", "save": True})
        self.assertFalse(again["ok"])
        self.assertIn("overwrite", again["error"])

    def test_get_missing_preset(self):
        payload = self.call(tools.get_preset, {"preset": "nope"})
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error_type"], "NotFoundError")

    def test_delete_requires_confirm(self):
        self.call(tools.create_preset, {"genre": "metal", "name": "Doomed", "save": True})
        refused = self.call(tools.delete_preset, {"preset": "doomed"})
        self.assertFalse(refused["ok"])
        confirmed = self.call(tools.delete_preset, {"preset": "doomed", "confirm": True})
        self.assertTrue(confirmed["ok"])
        self.assertEqual(self.call(tools.list_presets)["count"], 0)

    # -- adjustment -------------------------------------------------------- #
    def test_adjust_does_not_touch_the_stored_preset_by_default(self):
        self.call(tools.create_preset, {"genre": "metalcore", "name": "Core", "save": True})
        before = self.call(tools.get_preset, {"preset": "core"})["preset"]["version"]

        adjusted = self.call(
            tools.adjust_preset, {"preset": "core", "instructions": "make the low end tighter"}
        )
        self.assertTrue(adjusted["ok"])
        self.assertTrue(adjusted["changes"])
        self.assertIn("NOT modified", adjusted["note"])

        after = self.call(tools.get_preset, {"preset": "core"})
        self.assertEqual(after["preset"]["version"], before)
        self.assertEqual(after["preset"]["version"], 1)

    def test_adjust_with_save_bumps_the_version(self):
        self.call(tools.create_preset, {"genre": "metalcore", "name": "Core", "save": True})
        adjusted = self.call(
            tools.adjust_preset,
            {"preset": "core", "instructions": "add more presence", "save": True},
        )
        self.assertTrue(adjusted["ok"])
        self.assertEqual(adjusted["saved"]["version"], 2)

    def test_adjust_can_save_as_a_new_preset(self):
        self.call(tools.create_preset, {"genre": "metalcore", "name": "Core", "save": True})
        result = self.call(
            tools.adjust_preset,
            {"preset": "core", "instructions": "less gain", "save_as": "Core Soft"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["saved"]["slug"], "core-soft")
        self.assertEqual(self.call(tools.list_presets)["count"], 2)

    def test_adjust_accepts_an_inline_config(self):
        created = self.call(tools.create_preset, {"genre": "ambient"})
        result = self.call(
            tools.adjust_preset,
            {"config": created["tone"], "instructions": "more reverb"},
        )
        self.assertTrue(result["ok"])
        self.assertTrue(any(change["field"] == "space.reverb_mix" for change in result["changes"]))

    def test_adjust_requires_a_target(self):
        payload = self.call(tools.adjust_preset, {"instructions": "tighter"})
        self.assertFalse(payload["ok"])
        self.assertIn("preset", payload["error"])

    # -- MIDI -------------------------------------------------------------- #
    def test_midi_status_is_honest_about_blockers(self):
        payload = self.call(tools.midi_status)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["ready"])
        joined = " ".join(payload["blockers"])
        self.assertIn("No output port", joined)
        self.assertIn("No CC mappings", joined)

    def test_full_midi_flow(self):
        ports = self.call(tools.list_midi_ports)
        self.assertTrue(ports["ok"])
        self.assertEqual(ports["count"], 1)

        selected = self.call(tools.select_midi_port, {"port": "ToneForge"})
        self.assertTrue(selected["ok"])

        mapped = self.call(tools.map_parameter, {"parameter": "amp_gain", "cc": 20})
        self.assertTrue(mapped["ok"])

        status = self.call(tools.midi_status)
        self.assertTrue(status["ready"], status["blockers"])

        sent = self.call(tools.set_parameter, {"parameter": "gain", "value": 80})
        self.assertTrue(sent["ok"])
        self.assertTrue(sent["sent"])
        self.assertEqual(sent["applied"], "unverified")
        self.assertEqual(sent["parameter"], "amp_gain")
        self.assertEqual(sent["conversion"], "80/100 -> CC 102")
        self.assertEqual(self.backend.sent, [(0, 0xB0, 20, 102)])

    def test_set_parameter_without_mapping_explains_the_fix(self):
        self.call(tools.select_midi_port, {"port": "ToneForge"})
        payload = self.call(tools.set_parameter, {"parameter": "amp_bass", "value": 50})
        self.assertFalse(payload["ok"])
        self.assertIn("toneforge_map_parameter", payload["error"])
        self.assertIn("21", payload["error"])  # suggested CC for amp_bass
        self.assertEqual(self.backend.sent, [])

    def test_send_midi_never_picks_a_port_on_its_own(self):
        payload = self.call(tools.send_midi, {"cc": 20, "value": 1})
        self.assertFalse(payload["ok"])
        self.assertIn("never sends", payload["error"])
        self.assertEqual(self.backend.sent, [])

    def test_send_midi_with_explicit_port(self):
        payload = self.call(tools.send_midi, {"cc": 20, "value": 99, "port": 0})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["bytes_hex"], "B0 14 63")
        self.assertEqual(self.backend.sent, [(0, 0xB0, 20, 99)])

    def test_invalid_cc_value_is_refused(self):
        payload = self.call(tools.send_midi, {"cc": 200, "value": 1, "port": 0})
        self.assertFalse(payload["ok"])
        self.assertIn("cc", payload["error"])

    def test_seed_suggested_layout(self):
        payload = self.call(tools.map_parameter, {"seed_suggested": True})
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["mappings"]), 13)
        self.assertIn("not an amplitu", payload["seeded"]["note"].casefold())

    def test_convention_mapping_is_flagged_when_used(self):
        self.call(tools.select_midi_port, {"port": "ToneForge"})
        self.call(tools.map_parameter, {"seed_suggested": True})
        payload = self.call(tools.set_parameter, {"parameter": "amp_presence", "value": 50})
        self.assertTrue(payload["ok"])
        self.assertIn("warning", payload)
        self.assertIn("suggested layout", payload["warning"])

    def test_mappings_can_be_listed_and_removed(self):
        self.call(tools.map_parameter, {"parameter": "amp_gain", "cc": 20})
        listed = self.call(tools.list_mappings)
        self.assertEqual(listed["count"], 1)
        self.assertIn("amp_bass", listed["unmapped_suggested"])

        removed = self.call(tools.remove_mapping, {"parameter": "amp_gain"})
        self.assertTrue(removed["ok"])
        self.assertEqual(self.call(tools.list_mappings)["count"], 0)

    def test_probe_uses_a_mapped_parameter(self):
        self.call(tools.select_midi_port, {"port": "ToneForge"})
        self.call(tools.map_parameter, {"parameter": "od_drive", "cc": 28})
        payload = self.call(tools.midi_probe, {"parameter": "od_drive"})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["values"], [0, 127, 64])
        self.assertEqual([entry[3] for entry in self.backend.sent], [0, 127, 64])

    def test_set_parameter_flags_preset_scope(self):
        self.call(tools.select_midi_port, {"port": "ToneForge"})
        self.call(tools.map_parameter, {"parameter": "amp_gain", "cc": 20})
        payload = self.call(tools.set_parameter, {"parameter": "amp_gain", "value": 40})
        self.assertIn("Preset-level", payload["scope_note"])
        self.assertEqual(payload["mapping"]["scope"], "preset")

    def test_global_scope_has_no_preset_warning(self):
        self.call(tools.select_midi_port, {"port": "ToneForge"})
        self.call(tools.map_parameter, {"parameter": "amp_master", "cc": 25, "scope": "global"})
        payload = self.call(tools.set_parameter, {"parameter": "amp_master", "value": 40})
        self.assertNotIn("scope_note", payload)

    def test_probe_rejects_oversized_sequence(self):
        payload = self.call(tools.midi_probe, {"cc": 20, "values": [1, 2, 3, 4, 5, 6, 7, 8, 9]})
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
