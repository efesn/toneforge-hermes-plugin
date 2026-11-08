"""Reference-audio analysis: measurement, derivation and the tool contract.

The synthetic fixtures are generated with ffmpeg (a low sine plus pink noise), so the
tests need no network and no third-party Python packages.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
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

class UrlGuardTests(unittest.TestCase):
    """The `url` argument reaches yt-dlp as an argv element, so it is guarded twice."""

    def setUp(self):
        self._real_resolve = reference_analysis._resolve_host

    def tearDown(self):
        reference_analysis._resolve_host = self._real_resolve

    def _resolve_to(self, *addresses):
        reference_analysis._resolve_host = lambda host, port: set(addresses)

    def test_option_like_values_are_refused(self):
        for value in ("-o", "--config-locations=/tmp/x", " -f bestaudio", "--exec", "-"):
            with self.assertRaises(reference_analysis.UrlRejected, msg=value):
                reference_analysis.validate_url(value)

    def test_only_http_and_https_are_fetched(self):
        for value in ("file:///etc/passwd", "ftp://example.com/a.mp3",
                      "javascript:alert(1)", "//example.com/a", "example.com/a.mp3"):
            with self.assertRaises(reference_analysis.UrlRejected, msg=value):
                reference_analysis.validate_url(value)

    def test_credentials_are_refused(self):
        with self.assertRaises(reference_analysis.UrlRejected):
            reference_analysis.validate_url("https://user:pass@example.com/a.mp3")

    def test_local_names_are_refused_without_dns(self):
        for value in ("http://localhost/", "http://printer.local/a.mp3",
                      "http://metadata.google.internal/x", "http://db.internal/"):
            with self.assertRaises(reference_analysis.UrlRejected, msg=value):
                reference_analysis.validate_url(value)

    def test_non_public_addresses_are_refused_after_resolution(self):
        blocked = {
            "loopback-v4": "127.0.0.1",
            "loopback-v6": "::1",
            "private-10": "10.1.2.3",
            "private-192": "192.168.1.10",
            "link-local": "169.254.1.1",
            "metadata": "169.254.169.254",
            "cgnat": "100.64.0.1",
            "unique-local-v6": "fd00::1",
            "unspecified": "0.0.0.0",
        }
        for label, addr in blocked.items():
            self._resolve_to(addr)
            with self.assertRaises(reference_analysis.UrlRejected, msg=label):
                reference_analysis.validate_url("https://example.com/a.mp3")

    def test_one_bad_address_in_a_mixed_answer_is_enough_to_refuse(self):
        self._resolve_to("93.184.216.34", "10.0.0.5")
        with self.assertRaises(reference_analysis.UrlRejected):
            reference_analysis.validate_url("https://example.com/a.mp3")

    def test_public_url_is_accepted_and_normalised(self):
        self._resolve_to("93.184.216.34")
        out = reference_analysis.validate_url("HTTPS://Example.COM/a/b.mp3?x=1#frag")
        self.assertEqual(out, "https://example.com/a/b.mp3?x=1")

    def test_double_dash_precedes_the_url_in_both_argvs(self):
        self._resolve_to("93.184.216.34")
        url = reference_analysis.validate_url("https://example.com/a.mp3")
        download = reference_analysis.download_argv("yt-dlp", url, "out.%(ext)s")
        meta = reference_analysis.metadata_argv("yt-dlp", url)
        self.assertEqual(download[-2:], ["--", url])
        self.assertEqual(meta[-2:], ["--", url])
        self.assertNotIn("--", download[:-2])
        self.assertEqual(download[-4:-2], ["-o", "out.%(ext)s"])

    def test_download_refuses_before_looking_for_yt_dlp(self):
        with self.assertRaises(reference_analysis.UrlRejected):
            reference_analysis.download("-o", tempfile.mkdtemp(prefix="tf-ref-"))

    def test_tool_reports_the_refusal_as_a_clean_error(self):
        self._resolve_to("169.254.169.254")
        payload = json.loads(tools.analyze_reference(
            {"url": "http://169.254.169.254/latest/meta-data/"}))
        self.assertFalse(payload["ok"])
        self.assertIn("non-public address", payload["error"])


class VersionTests(unittest.TestCase):
    def test_preset_records_carry_the_manifest_version(self):
        from _pkg import preset_store
        manifest = (pathlib.Path(preset_store.__file__).with_name("plugin.yaml")
                    .read_text(encoding="utf-8"))
        declared = re.search(r"^version:\s*(\S+)", manifest, re.M).group(1).strip('"')
        self.assertEqual(preset_store.PLUGIN_VERSION, declared)
