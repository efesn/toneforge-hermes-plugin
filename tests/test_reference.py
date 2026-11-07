"""Reference-audio analysis: measurement, derivation and the tool contract.

The synthetic fixtures are generated with ffmpeg (a low sine plus pink noise), so the
tests need no network and no third-party Python packages.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest

from _pkg import reference_analysis, schemas, tools

FFMPEG = shutil.which("ffmpeg") or os.environ.get("TONEFORGE_FFMPEG")


def make_fixture(path: str, *, low_hz: float = 82.41, seconds: int = 6) -> None:
    cmd = [
        FFMPEG, "-v", "error", "-y",
        "-f", "lavfi", "-i", f"sine=frequency={low_hz}:duration={seconds}:sample_rate=44100",
        "-f", "lavfi", "-i", f"anoisesrc=d={seconds}:c=pink:r=44100:a=0.05",
        "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=shortest,volume=0.8",
        "-ac", "2", path,
    ]
    subprocess.run(cmd, check=True, timeout=120)


@unittest.skipUnless(FFMPEG, "ffmpeg is required for the analysis tests")
class AnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="toneforge-test-")
        cls.low = os.path.join(cls.tmp, "low.wav")
        cls.high = os.path.join(cls.tmp, "high.wav")
        cls.fade = os.path.join(cls.tmp, "fade.wav")
        make_fixture(cls.low, low_hz=82.41)
        make_fixture(cls.high, low_hz=196.0)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", cls.low,
                        "-af", "afade=t=out:st=2:d=4", cls.fade], check=True, timeout=120)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_low_peaks_are_resolved_fine_enough_for_tuning(self):
        result = reference_analysis.analyze(self.low, start=0, end=5)
        # one 16 kHz/4096 bin is ~90 cents at 74 Hz, which cannot identify a tuning
        self.assertLessEqual(result["low_peak_resolution_hz"], 1.0)

    def test_clip_fade_is_not_reported_as_a_reverb_tail(self):
        result = reference_analysis.analyze(self.fade, start=0, end=5)
        # a 4 s fade-out must never be sold as reverb: either it is unusable or it is short
        tail = result["tail"]["t30_s"]
        self.assertTrue(tail is None or tail <= 2.5, f"fade reported as a {tail} s tail")

    def test_analysis_reports_bands_and_shape(self):
        result = reference_analysis.analyze(self.low, start=0, end=5)
        self.assertIn("octave_bands_db", result)
        self.assertIn("shape", result)
        self.assertGreater(result["shape"]["centroid_hz"], 0)
        self.assertLess(result["shape"]["slope_db_per_oct"], 0)
        self.assertTrue(result["caveats"], "the full-mix caveat must always travel with the numbers")

    def test_low_peak_finds_the_tuning_reference(self):
        result = reference_analysis.analyze(self.low, start=0, end=5)
        hz = [peak["hz"] for peak in result["low_peaks"]]
        self.assertTrue(any(abs(f - 82.41) < 1.5 for f in hz), f"expected an 82.4 Hz partial, got {hz}")
        self.assertIsNotNone(result["tuning"]["guess"])

    def test_overrides_are_complete_and_bounded(self):
        metrics = reference_analysis.analyze(self.low, start=0, end=5)
        overrides = reference_analysis.derive_overrides(metrics)
        for key in ("params", "eq", "gate", "space", "why"):
            self.assertIn(key, overrides)
        for key, value in overrides["params"].items():
            self.assertGreaterEqual(value, 0, key)
            self.assertLessEqual(value, 100, key)
        self.assertLessEqual(overrides["eq"]["high_cut_hz"], 12000)
        self.assertGreaterEqual(overrides["eq"]["low_cut_hz"], 90)
        self.assertEqual(len(overrides["eq"]["bands"]), 7)

    def test_darker_audio_gets_darker_settings(self):
        dark = reference_analysis.derive_overrides(reference_analysis.analyze(self.low, start=0, end=5))
        self.assertLessEqual(dark["eq"]["high_cut_hz"], 12000)

    def test_missing_file_is_an_analysis_error(self):
        with self.assertRaises(reference_analysis.AnalysisError):
            reference_analysis.analyze(os.path.join(self.tmp, "nope.wav"))


class ToolContractTests(unittest.TestCase):
    def test_schema_is_registered_and_handler_exists(self):
        names = {schema["name"] for schema in schemas.TOOLS}
        self.assertIn("toneforge_analyze_reference", names)
        self.assertIn("toneforge_analyze_reference", tools.HANDLERS)
        schema = schemas.get("toneforge_analyze_reference")
        self.assertIn("path", schema["parameters"]["properties"])
        self.assertIn("url", schema["parameters"]["properties"])
        self.assertIn("start_s", schema["parameters"]["properties"])

    def test_missing_arguments_are_refused_with_json(self):
        payload = json.loads(tools.analyze_reference({}))
        self.assertFalse(payload["ok"])
        self.assertIn("path", payload["error"])

    def test_end_before_start_is_refused(self):
        payload = json.loads(tools.analyze_reference({"path": "x.wav", "start_s": 10, "end_s": 5}))
        self.assertFalse(payload["ok"])


if __name__ == "__main__":
    unittest.main()
