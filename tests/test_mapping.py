"""CC mapping storage and value conversion."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from _pkg import midi_map, validation


class ConversionTests(unittest.TestCase):
    def _mapping(self, **overrides):
        base = {
            "cc": 20, "channel": 1, "min": 0, "max": 127,
            "param_min": 0, "param_max": 100, "invert": False,
        }
        base.update(overrides)
        return base

    def test_endpoints(self):
        mapping = self._mapping()
        self.assertEqual(midi_map.to_cc(0, mapping), 0)
        self.assertEqual(midi_map.to_cc(100, mapping), 127)

    def test_midpoint(self):
        self.assertEqual(midi_map.to_cc(50, self._mapping()), 64)

    def test_quarter(self):
        self.assertEqual(midi_map.to_cc(25, self._mapping()), 32)

    def test_values_are_clamped_to_param_range(self):
        self.assertEqual(midi_map.to_cc(-20, self._mapping()), 0)
        self.assertEqual(midi_map.to_cc(500, self._mapping()), 127)

    def test_custom_param_range(self):
        mapping = self._mapping(param_min=0, param_max=10)
        self.assertEqual(midi_map.to_cc(5, mapping), 64)
        self.assertEqual(midi_map.to_cc(10, mapping), 127)

    def test_custom_cc_range(self):
        mapping = self._mapping(min=10, max=20)
        self.assertEqual(midi_map.to_cc(0, mapping), 10)
        self.assertEqual(midi_map.to_cc(100, mapping), 20)

    def test_invert_mirrors(self):
        mapping = self._mapping(invert=True)
        self.assertEqual(midi_map.to_cc(0, mapping), 127)
        self.assertEqual(midi_map.to_cc(100, mapping), 0)

    def test_broken_range_is_refused(self):
        with self.assertRaises(validation.ValidationError):
            midi_map.to_cc(50, self._mapping(param_min=100, param_max=100))


class CanonicalNameTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(midi_map.canonical_name("gain"), "amp_gain")
        self.assertEqual(midi_map.canonical_name("Amp Gain"), "amp_gain")
        self.assertEqual(midi_map.canonical_name("mids"), "amp_mid")
        self.assertEqual(midi_map.canonical_name("reverb"), "reverb_mix")

    def test_unknown_names_are_kept_as_identifiers(self):
        self.assertEqual(midi_map.canonical_name("wah pedal"), "wah_pedal")

    def test_invalid_names_are_refused(self):
        with self.assertRaises(validation.ValidationError):
            midi_map.canonical_name("amp gain; rm -rf /")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = midi_map.MappingStore(root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_and_get(self):
        self.store.add("amp_gain", 20)
        entry = self.store.get("gain")
        self.assertEqual(entry["cc"], 20)
        self.assertEqual(entry["channel"], 1)

    def test_duplicate_requires_overwrite(self):
        self.store.add("amp_gain", 20)
        with self.assertRaises(validation.ConflictError):
            self.store.add("amp_gain", 21)
        self.store.add("amp_gain", 21, overwrite=True)
        self.assertEqual(self.store.get("amp_gain")["cc"], 21)

    def test_invalid_cc_is_refused(self):
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_gain", 128)
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_gain", -1)

    def test_invalid_channel_is_refused(self):
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_gain", 20, channel=0)
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_gain", 20, channel=17)

    def test_inverted_cc_range_is_refused(self):
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_gain", 20, minimum=100, maximum=10)

    def test_scope_defaults_to_preset_and_is_validated(self):
        self.store.add("amp_gain", 20)
        self.assertEqual(self.store.get("amp_gain")["scope"], "preset")
        self.store.add("amp_master", 25, scope="global")
        self.assertEqual(self.store.get("amp_master")["scope"], "global")
        with self.assertRaises(validation.ValidationError):
            self.store.add("amp_bass", 21, scope="song")

    def test_remove(self):
        self.store.add("amp_gain", 20)
        removed = self.store.remove("amp_gain")
        self.assertIn("amp_gain", removed)
        self.assertIsNone(self.store.get("amp_gain"))
        with self.assertRaises(validation.NotFoundError):
            self.store.remove("amp_gain")

    def test_seed_suggested_is_idempotent(self):
        added = self.store.seed_suggested()
        self.assertEqual(len(added), len(midi_map.SUGGESTED_MAPPINGS))
        self.assertEqual(self.store.seed_suggested(), [])
        self.assertEqual(self.store.get("amp_gain")["assigned_in"], "toneforge-convention")

    def test_corrupt_file_is_reported(self):
        (self.root / "midi_map.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(validation.ToneForgeError):
            self.store.all()


if __name__ == "__main__":
    unittest.main()
