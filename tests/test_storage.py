"""Preset storage: round trips, overwrite protection and path safety."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from _pkg import preset_store, tone_engine, validation


def _tone(name="Test Tone"):
    return tone_engine.build_tone(genre="industrial metal", tuning="drop d", name=name)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.store = preset_store.PresetStore(root=self.root)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_load_round_trip(self):
        record = self.store.save(_tone(), name="Rammstein Sonne Drop D")
        self.assertEqual(record["version"], 1)
        self.assertEqual(record["slug"], "rammstein-sonne-drop-d")
        loaded = self.store.load("rammstein-sonne-drop-d")
        self.assertEqual(loaded["name"], "Rammstein Sonne Drop D")
        self.assertEqual(loaded["config"]["params"], record["config"]["params"])
        self.assertEqual(loaded["schema_version"], preset_store.SCHEMA_VERSION)

    def test_file_is_json_on_disk(self):
        self.store.save(_tone(), name="Plain")
        path = self.root / "plain.json"
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["name"], "Plain")

    def test_duplicate_without_overwrite_is_refused(self):
        self.store.save(_tone(), name="Dup")
        with self.assertRaises(validation.ConflictError) as ctx:
            self.store.save(_tone(), name="Dup")
        self.assertIn("overwrite", str(ctx.exception))

    def test_overwrite_bumps_version_and_keeps_created_at(self):
        first = self.store.save(_tone(), name="Bump")
        second = self.store.save(_tone(), name="Bump", overwrite=True)
        self.assertEqual(second["version"], 2)
        self.assertEqual(first["created_at"], second["created_at"])

    def test_list_is_newest_first(self):
        self.store.save(_tone(), name="Older")
        self.store.save(_tone(), name="Newer")
        items = self.store.list()
        self.assertEqual(len(items), 2)
        self.assertGreaterEqual(items[0]["updated_at"], items[1]["updated_at"])
        self.assertEqual({item["slug"] for item in items}, {"older", "newer"})

    def test_delete_requires_confirm(self):
        self.store.save(_tone(), name="Doomed")
        with self.assertRaises(validation.ValidationError):
            self.store.delete("doomed")
        self.assertTrue(self.store.exists("doomed"))
        removed = self.store.delete("doomed", confirm=True)
        self.assertEqual(removed["slug"], "doomed")
        self.assertFalse(self.store.exists("doomed"))

    def test_missing_preset_raises_not_found(self):
        with self.assertRaises(validation.NotFoundError):
            self.store.load("does-not-exist")

    def test_partial_name_match_loads_unique_preset(self):
        self.store.save(_tone(), name="Metallica Thrash Rhythm")
        loaded = self.store.load("metallica")
        self.assertEqual(loaded["slug"], "metallica-thrash-rhythm")

    def test_ambiguous_partial_match_is_refused(self):
        self.store.save(_tone(), name="Metal One")
        self.store.save(_tone(), name="Metal Two")
        with self.assertRaises(validation.ValidationError) as ctx:
            self.store.load("metal")
        self.assertIn("several presets", str(ctx.exception))

    def test_path_traversal_in_slug_is_refused(self):
        for bad in ("../escape", "..", "/abs/path", "a/b"):
            with self.assertRaises(validation.ValidationError, msg=bad):
                self.store.path_for(bad)

    def test_traversal_via_name_is_neutralised(self):
        record = self.store.save(_tone(), name="../../etc/passwd")
        self.assertNotIn("..", record["slug"])
        self.assertNotIn("/", record["slug"])
        self.assertTrue((self.root / f"{record['slug']}.json").exists())
        # Nothing was written outside the store directory.
        self.assertFalse((self.root.parent / "etc").exists())
        self.assertEqual(len(list(self.root.glob("*.json"))), 1)

    def test_writes_are_atomic_no_temp_files_left(self):
        self.store.save(_tone(), name="Atomic")
        leftovers = [p.name for p in self.root.iterdir() if p.name.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_corrupt_file_is_reported_not_crashed(self):
        (self.root / "broken.json").write_text("{not json", encoding="utf-8")
        self.assertEqual(self.store.list(), [])
        with self.assertRaises(validation.ToneForgeError):
            self.store.load("broken")

    def test_future_schema_is_refused(self):
        (self.root / "future.json").write_text(
            json.dumps({"schema_version": 99, "name": "Future", "config": {}}), encoding="utf-8"
        )
        with self.assertRaises(validation.ToneForgeError) as ctx:
            self.store.load("future")
        self.assertIn("newer ToneForge", str(ctx.exception))

    def test_unicode_name_gets_ascii_slug(self):
        record = self.store.save(_tone(), name="Türkçe Ton — Ağır")
        self.assertTrue(record["slug"].isascii())
        self.assertEqual(self.store.load(record["slug"])["name"], "Türkçe Ton — Ağır")


class DataDirTests(unittest.TestCase):
    def test_env_override_is_honoured(self):
        with tempfile.TemporaryDirectory() as tmp:
            import os

            previous = os.environ.get("TONEFORGE_DATA_DIR")
            os.environ["TONEFORGE_DATA_DIR"] = tmp
            try:
                self.assertEqual(preset_store.data_dir().resolve(), Path(tmp).resolve())
            finally:
                if previous is None:
                    os.environ.pop("TONEFORGE_DATA_DIR", None)
                else:
                    os.environ["TONEFORGE_DATA_DIR"] = previous

    def test_hermes_home_is_used_when_plugin_storage_is_unavailable(self):
        """A CLI script must write to the same home the running agent reads."""
        if preset_store._plugin_data_dir is not None:
            self.skipTest("running inside Hermes; plugin_data_dir takes precedence")
        import os

        with tempfile.TemporaryDirectory() as tmp:
            previous = {key: os.environ.get(key) for key in ("HERMES_HOME", "TONEFORGE_DATA_DIR")}
            os.environ.pop("TONEFORGE_DATA_DIR", None)
            os.environ["HERMES_HOME"] = tmp
            try:
                self.assertEqual(
                    preset_store.data_dir().resolve(),
                    Path(tmp).resolve() / "plugin-data" / "tone-forge",
                )
            finally:
                for key, value in previous.items():
                    if value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
