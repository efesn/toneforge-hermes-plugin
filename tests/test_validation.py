"""Input validation: the security boundary for names, ranges and text."""

from __future__ import annotations

import unittest

from _pkg import validation as V


class CoerceIntTests(unittest.TestCase):
    def test_accepts_int_float_and_numeric_string(self):
        self.assertEqual(V.coerce_int(75, "gain", lo=0, hi=100), 75)
        self.assertEqual(V.coerce_int("75", "gain", lo=0, hi=100), 75)
        self.assertEqual(V.coerce_int(75.0, "gain", lo=0, hi=100), 75)

    def test_rejects_fraction(self):
        with self.assertRaises(V.ValidationError):
            V.coerce_int(75.5, "gain", lo=0, hi=100)

    def test_rejects_bool(self):
        with self.assertRaises(V.ValidationError):
            V.coerce_int(True, "gain", lo=0, hi=100)

    def test_rejects_non_numeric(self):
        with self.assertRaises(V.ValidationError):
            V.coerce_int("loud", "gain")

    def test_rejects_out_of_range(self):
        with self.assertRaises(V.ValidationError):
            V.coerce_int(101, "gain", lo=0, hi=100)
        with self.assertRaises(V.ValidationError):
            V.coerce_int(-1, "gain", lo=0, hi=100)

    def test_rejects_nan_and_infinity(self):
        with self.assertRaises(V.ValidationError):
            V.coerce_int(float("nan"), "gain")
        with self.assertRaises(V.ValidationError):
            V.coerce_int(float("inf"), "gain")

    def test_none_returns_default(self):
        self.assertIsNone(V.coerce_int(None, "gain"))
        self.assertEqual(V.coerce_int(None, "gain", default=7), 7)
        self.assertEqual(V.coerce_int("", "gain", default=7), 7)


class TextTests(unittest.TestCase):
    def test_trims_and_limits(self):
        self.assertEqual(V.require_text("  drop D  ", "tuning"), "drop D")
        with self.assertRaises(V.ValidationError):
            V.require_text("x" * 300, "name", max_len=280)

    def test_required_rejects_empty(self):
        with self.assertRaises(V.ValidationError):
            V.require_text("   ", "name", required=True)

    def test_rejects_control_characters(self):
        with self.assertRaises(V.ValidationError):
            V.require_text("drop\x00D", "tuning")

    def test_rejects_non_string(self):
        with self.assertRaises(V.ValidationError):
            V.require_text(12, "name")


class ChoiceTests(unittest.TestCase):
    def test_alias_resolution_is_case_insensitive(self):
        self.assertEqual(V.normalize_choice("Drop D", "tuning", {"drop d": "drop_d"}), "drop_d")
        self.assertEqual(V.normalize_choice("drop_d", "tuning", {"drop d": "drop_d"}), "drop_d")
        self.assertEqual(V.normalize_choice("DROP-D", "tuning", {"drop d": "drop_d"}), "drop_d")

    def test_unknown_choice_lists_options(self):
        with self.assertRaises(V.ValidationError) as ctx:
            V.normalize_choice("bebop", "tuning", {"drop d": "drop_d", "standard": "standard"})
        self.assertIn("standard", str(ctx.exception))

    def test_turkish_characters_fold(self):
        self.assertEqual(V.normalize_choice("Sıkı", "purpose", {"siki": "tight"}), "tight")


class SlugTests(unittest.TestCase):
    def test_slugify_produces_safe_stem(self):
        self.assertEqual(V.slugify("Rammstein — Sonne (Drop D)!"), "rammstein-sonne-drop-d")
        self.assertEqual(V.slugify("   "), "preset")
        self.assertEqual(V.slugify("Ünlü Türkçe İsim"), "unlu-turkce-isim")

    def test_validate_slug_blocks_traversal(self):
        for bad in ("../evil", "..", "/etc/passwd", "a/b", "a\\b", ".hidden", "C:evil", ""):
            with self.assertRaises(V.ValidationError, msg=bad):
                V.validate_slug(bad)

    def test_validate_slug_accepts_normal(self):
        self.assertEqual(V.validate_slug("industrial-metal-drop-d"), "industrial-metal-drop-d")


class MappingNameTests(unittest.TestCase):
    def test_accepts_identifier(self):
        self.assertEqual(V.validate_mapping_name("amp_gain"), "amp_gain")
        self.assertEqual(V.validate_mapping_name("Amp Gain"), "amp_gain")

    def test_rejects_bad_names(self):
        for bad in ("amp gain!", "9lives", "", "a" * 40, "amp-gain"):
            with self.assertRaises(V.ValidationError, msg=bad):
                V.validate_mapping_name(bad)


class ClampTests(unittest.TestCase):
    def test_clamps(self):
        self.assertEqual(V.clamp_int(140, 0, 100), 100)
        self.assertEqual(V.clamp_int(-5, 0, 100), 0)
        self.assertEqual(V.clamp_int(50, 0, 100), 50)


if __name__ == "__main__":
    unittest.main()
