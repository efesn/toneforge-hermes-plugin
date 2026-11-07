"""Tone generation and adjustment behaviour."""

from __future__ import annotations

import copy
import unittest

from _pkg import tone_engine, tone_profiles


class CreateToneTests(unittest.TestCase):
    def test_every_profile_builds_a_complete_recipe(self):
        for key in tone_profiles.PROFILES:
            with self.subTest(profile=key):
                cfg = tone_engine.build_tone(genre=key)
                self.assertEqual(cfg["genre"], key)
                chain = cfg["signal_chain"]
                self.assertGreaterEqual(len(chain), 3)
                self.assertEqual([item["order"] for item in chain], list(range(1, len(chain) + 1)))
                stages = [item["stage"] for item in chain]
                self.assertIn("Amplifier", stages)
                self.assertIn("Cabinet + microphone", stages)
                for param in tone_engine.PARAM_KEYS:
                    self.assertGreaterEqual(cfg["params"][param], 0)
                    self.assertLessEqual(cfg["params"][param], 100)
                self.assertTrue(cfg["why"])
                self.assertIn("not a reproduction", cfg["disclaimer"])

    def test_generation_is_deterministic(self):
        first = tone_engine.build_tone(genre="industrial metal", tuning="drop d")
        second = tone_engine.build_tone(genre="industrial metal", tuning="drop d")
        self.assertEqual(first, second)

    def test_reference_becomes_inspiration_not_claim(self):
        cfg = tone_engine.build_tone(genre="industrial metal", reference="Rammstein - Sonne")
        self.assertEqual(cfg["reference"], "Rammstein - Sonne")
        self.assertIn("inspired by", cfg["description"])
        self.assertIn("not a reproduction", cfg["disclaimer"])

    def test_amp_block_is_a_family_not_a_model_name(self):
        cfg = tone_engine.build_tone(genre="metalcore")
        self.assertNotIn("model", cfg["amp"])
        self.assertIn("category", cfg["amp"])
        self.assertIn("family", cfg["amp"])
        self.assertTrue(cfg["amp"]["search_terms"])

    def test_lower_tuning_trims_bass_and_moves_high_pass(self):
        standard = tone_engine.build_tone(genre="modern metal", tuning="standard")
        drop_c = tone_engine.build_tone(genre="modern metal", tuning="drop C")
        self.assertLess(drop_c["params"]["bass"], standard["params"]["bass"])
        self.assertLess(drop_c["eq"]["low_cut_hz"], standard["eq"]["low_cut_hz"])

    def test_active_pickups_need_less_gain_than_single_coils(self):
        humbucker = tone_engine.build_tone(genre="thrash", pickup="humbucker")
        single = tone_engine.build_tone(genre="thrash", pickup="single coil")
        active = tone_engine.build_tone(genre="thrash", pickup="active humbucker")
        self.assertGreater(single["params"]["gain"], humbucker["params"]["gain"])
        self.assertLess(active["params"]["gain"], humbucker["params"]["gain"])

    def test_purpose_shifts_the_recipe(self):
        rhythm = tone_engine.build_tone(genre="lead profile", purpose="rhythm")
        lead = tone_engine.build_tone(genre="lead profile", purpose="lead")
        self.assertGreater(lead["params"]["mid"], rhythm["params"]["mid"])
        self.assertGreater(lead["space"]["delay_mix"], rhythm["space"]["delay_mix"])

    def test_gain_level_override_is_exact(self):
        cfg = tone_engine.build_tone(genre="modern metal", gain_level=37)
        self.assertEqual(cfg["params"]["gain"], 37)
        self.assertTrue(any("Gain set to 37" in line for line in cfg["why"]))

    def test_gain_level_out_of_range_is_rejected(self):
        with self.assertRaises(Exception):
            tone_engine.build_tone(genre="modern metal", gain_level=140)

    def test_unknown_genre_falls_back_with_an_assumption(self):
        cfg = tone_engine.build_tone(genre="zydeco polka")
        self.assertTrue(cfg["assumptions"])
        self.assertIn("not in the profile library", " ".join(cfg["assumptions"]))

    def test_defaults_are_reported_not_hidden(self):
        cfg = tone_engine.build_tone(genre="industrial metal")
        joined = " ".join(cfg["assumptions"])
        self.assertIn("No tuning given", joined)
        self.assertIn("No pickup given", joined)


class InstructionTests(unittest.TestCase):
    def _delta(self, instructions, profile="industrial metal", param="bass"):
        base = tone_engine.build_tone(genre=profile)
        tuned = tone_engine.build_tone(genre=profile, instructions=instructions)
        return tuned["params"][param] - base["params"][param]

    def test_tighter_reduces_bass(self):
        self.assertLess(self._delta("make it tighter"), 0)

    def test_more_mids_increases_mid(self):
        self.assertGreater(self._delta("increase the mids", param="mid"), 0)

    def test_less_gain_reduces_gain(self):
        self.assertLess(self._delta("reduce the gain", param="gain"), 0)

    def test_heavier_adds_gain(self):
        self.assertGreater(self._delta("make it heavier", param="gain"), 0)

    def test_explicit_number_wins(self):
        cfg = tone_engine.build_tone(genre="modern metal", instructions="set the amp gain to 75")
        self.assertEqual(cfg["params"]["gain"], 75)
        self.assertTrue(any("Set amp gain to 75" in line for line in cfg["instructions_applied"]))

    def test_explicit_number_out_of_range_is_ignored_with_note(self):
        cfg = tone_engine.build_tone(genre="modern metal", instructions="set gain to 140")
        self.assertLessEqual(cfg["params"]["gain"], 100)
        self.assertTrue(any("Ignored gain = 140" in line for line in cfg["instructions_applied"]))

    def test_no_gate_disables_and_is_not_re_enabled(self):
        cfg = tone_engine.build_tone(genre="industrial metal", instructions="remove the noise gate")
        self.assertFalse(cfg["gate"]["enabled"])
        self.assertNotIn("Noise gate", [item["stage"] for item in cfg["signal_chain"]])

    def test_tighter_gate_is_not_overridden_by_gate_catch_all(self):
        base = tone_engine.build_tone(genre="industrial metal")
        tighter = tone_engine.build_tone(genre="industrial metal", instructions="tighter gate")
        self.assertLess(tighter["gate"]["threshold_db"], base["gate"]["threshold_db"])

    def test_muddy_instruction_moves_several_controls(self):
        cfg = tone_engine.build_tone(genre="metalcore", instructions="make it less muddy")
        notes = " ".join(cfg["instructions_applied"])
        self.assertIn("mud", notes.lower())

    def test_djent_tightens_more_than_a_plain_request(self):
        plain = tone_engine.build_tone(genre="modern metal")
        djent = tone_engine.build_tone(genre="modern metal", instructions="make it djenty")
        self.assertGreater(djent["eq"]["low_cut_hz"], plain["eq"]["low_cut_hz"])

    def test_turkish_instruction_is_understood(self):
        self.assertLess(self._delta("daha sıkı olsun"), 0)


class GateCoherenceTests(unittest.TestCase):
    """The pedal list, the gate block and the rendered chain must agree."""

    def test_removing_the_gate_removes_the_pedal(self):
        cfg = tone_engine.build_tone(genre="industrial metal", instructions="remove the noise gate")
        self.assertFalse(cfg["gate"]["enabled"])
        self.assertFalse(any("gate" in pedal["type"].casefold() for pedal in cfg["pedals"]))
        self.assertNotIn("Noise gate", [stage["stage"] for stage in cfg["signal_chain"]])

    def test_gate_pedal_settings_follow_the_gate(self):
        cfg = tone_engine.build_tone(genre="industrial metal", instructions="tighter gate")
        gate_pedals = [p for p in cfg["pedals"] if "gate" in p["type"].casefold()]
        self.assertEqual(len(gate_pedals), 1)
        self.assertEqual(gate_pedals[0]["settings"]["threshold_db"], cfg["gate"]["threshold_db"])
        self.assertEqual(gate_pedals[0]["settings"]["decay_ms"], cfg["gate"]["decay_ms"])

    def test_clean_purpose_drops_the_gate_pedal(self):
        cfg = tone_engine.build_tone(genre="metalcore", purpose="clean")
        self.assertFalse(cfg["gate"]["enabled"])
        self.assertFalse(any("gate" in pedal["type"].casefold() for pedal in cfg["pedals"]))

    def test_enabling_the_gate_on_a_gateless_profile_adds_the_pedal(self):
        cfg = tone_engine.build_tone(genre="clean", purpose="rhythm")
        self.assertTrue(cfg["gate"]["enabled"])
        self.assertTrue(any("gate" in pedal["type"].casefold() for pedal in cfg["pedals"]))
        self.assertEqual(cfg["signal_chain"][0]["stage"], "Noise gate")

    def test_empty_instruction_is_a_no_op(self):
        base = tone_engine.build_tone(genre="thrash")
        same = tone_engine.build_tone(genre="thrash", instructions="   ")
        self.assertEqual(base["params"], same["params"])


class AdjustTests(unittest.TestCase):
    def setUp(self):
        self.original = tone_engine.build_tone(genre="industrial metal", tuning="drop d")

    def test_adjust_returns_changes_and_leaves_input_untouched(self):
        snapshot = copy.deepcopy(self.original)
        updated, changes, explanations = tone_engine.adjust_tone(
            self.original, "make the low end tighter"
        )
        self.assertEqual(self.original, snapshot, "adjust_tone must not mutate its input")
        self.assertTrue(changes)
        self.assertTrue(explanations)
        self.assertNotEqual(updated["params"], self.original["params"])
        fields = {change["field"] for change in changes}
        self.assertIn("params.bass", fields)

    def test_adjust_reports_before_and_after(self):
        _, changes, _ = tone_engine.adjust_tone(self.original, "set gain to 60")
        gain_change = next(c for c in changes if c["field"] == "params.gain")
        self.assertEqual(gain_change["after"], 60)
        self.assertEqual(gain_change["before"], self.original["params"]["gain"])

    def test_unrecognised_instruction_changes_nothing_and_says_so(self):
        updated, changes, explanations = tone_engine.adjust_tone(self.original, "make it sound purple")
        self.assertEqual(changes, [])
        self.assertIn("No recognised adjustment", explanations[0])
        self.assertEqual(updated["params"], self.original["params"])

    def test_purpose_switch_reshapes(self):
        updated, changes, _ = tone_engine.adjust_tone(self.original, "make it a lead tone")
        self.assertEqual(updated["purpose"], "lead")
        self.assertTrue(any(c["field"] == "purpose" for c in changes))

    def test_retune_recomputes_compensation(self):
        updated, _, _ = tone_engine.adjust_tone(self.original, "retune for drop c", tuning="drop C")
        self.assertEqual(updated["tuning"], "drop_c")
        self.assertLess(updated["params"]["bass"], self.original["params"]["bass"])


if __name__ == "__main__":
    unittest.main()
