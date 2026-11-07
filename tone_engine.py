"""Tone generation and adjustment engine.

The engine is deterministic: the same request always produces the same recipe.
That matters because a preset is a document the player edits by hand inside
AmpliTube, and because tests need to assert on real behaviour rather than on
"something plausible".

Pipeline
--------
1. resolve genre -> profile (aliases, then fuzzy keyword match)
2. copy the profile's base parameters
3. apply tuning compensation, pickup compensation, purpose shaping
4. apply free-text instruction modifiers (ordered, each at most once)
5. apply explicit numeric overrides last ("set the gain to 75")
6. render the signal chain, explanations and assumptions
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from . import tone_profiles as P
from .validation import ValidationError, clamp_int, normalize_choice, require_text
from .validation import _fold as V_fold

PARAM_KEYS = ("gain", "bass", "mid", "treble", "presence", "master")
PARAM_LABELS = {
    "gain": "Amp gain",
    "bass": "Bass",
    "mid": "Mid",
    "treble": "Treble",
    "presence": "Presence",
    "master": "Master",
}
EQ_FREQS = (100, 200, 400, 800, 1600, 3200, 6400)
MAX_CHAIN_NOTES = 6


# --------------------------------------------------------------------------- #
# Genre resolution
# --------------------------------------------------------------------------- #
def resolve_genre(genre: Optional[str], reference: Optional[str] = None) -> tuple[str, list[str]]:
    """Return (profile_key, assumptions) for a free-text genre/reference pair."""
    assumptions: list[str] = []
    haystacks = [t for t in (genre, reference) if t]

    if haystacks:
        # 0) a canonical profile key passed straight through ("industrial_metal")
        for text in haystacks:
            folded_key = V_fold(text).replace(" ", "_")
            if folded_key in P.PROFILES:
                return folded_key, assumptions

        # 1) exact alias match, longest alias first so "industrial metal" beats "metal".
        aliases: list[tuple[str, str]] = []
        for key, profile in P.PROFILES.items():
            for alias in profile["aliases"]:
                folded_alias = V_fold(alias)
                if folded_alias:
                    aliases.append((folded_alias, key))
        aliases.sort(key=lambda pair: len(pair[0]), reverse=True)
        folded = " ".join(V_fold(text) for text in haystacks)
        for alias, key in aliases:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", folded):
                return key, assumptions

        # 2) token overlap against labels/aliases.
        tokens = {t for t in re.split(r"[^a-z0-9]+", folded) if len(t) > 3}
        best_key, best_score = None, 0
        for key, profile in P.PROFILES.items():
            vocabulary = {V_fold(profile["label"])}
            vocabulary.update(V_fold(alias) for alias in profile["aliases"])
            vocab_tokens = {t for v in vocabulary for t in re.split(r"[^a-z0-9]+", v) if len(t) > 3}
            score = len(tokens & vocab_tokens)
            if score > best_score:
                best_key, best_score = key, score
        if best_key and best_score >= 2:
            assumptions.append(
                f"Genre {genre or reference!r} matched the {P.PROFILES[best_key]['label']} profile "
                "by keyword overlap; the profile is a starting point, not a transcription."
            )
            return best_key, assumptions

    fallback = "modern_metal"
    if genre:
        assumptions.append(
            f"Genre {genre!r} is not in the profile library; used {P.PROFILES[fallback]['label']} "
            "as the closest general-purpose starting point."
        )
    else:
        assumptions.append(
            f"No genre given; used {P.PROFILES[fallback]['label']} as a neutral high-gain default."
        )
    return fallback, assumptions


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _bump(cfg: dict, key: str, delta: int) -> int:
    """Adjust one parameter by *delta*, clamped to 0-100; return the applied delta."""
    if key not in cfg["params"]:
        return 0
    before = cfg["params"][key]
    after = clamp_int(before + delta, 0, 100)
    cfg["params"][key] = after
    return after - before


def _band(cfg: dict, hz: int) -> dict:
    for band in cfg["eq"]["bands"]:
        if band["hz"] == hz:
            return band
    band = {"hz": hz, "db": 0}
    cfg["eq"]["bands"].append(band)
    cfg["eq"]["bands"].sort(key=lambda b: b["hz"])
    return band


def _bump_band(cfg: dict, hz: int, delta: float) -> float:
    band = _band(cfg, hz)
    before = band["db"]
    band["db"] = round(max(-12.0, min(12.0, before + delta)), 1)
    return round(band["db"] - before, 1)


def _set_space(cfg: dict, key: str, value: float) -> None:
    cfg["space"][key] = round(max(0.0, min(0.6, value)), 2)


def _has_pedal(cfg: dict, needle: str) -> bool:
    needle = needle.casefold()
    return any(needle in pedal["type"].casefold() for pedal in cfg["pedals"])


def _add_pedal(cfg: dict, pedal: dict) -> bool:
    """Append a pedal unless one of that family is already present."""
    family = pedal["type"].casefold().split("/")[0].strip()
    if _has_pedal(cfg, family):
        return False
    cfg["pedals"].append(pedal)
    return True


def _remove_pedal_family(cfg: dict, needle: str) -> bool:
    needle = needle.casefold()
    before = len(cfg["pedals"])
    cfg["pedals"] = [p for p in cfg["pedals"] if needle not in p["type"].casefold()]
    return len(cfg["pedals"]) != before


def _bump_gate(cfg: dict, threshold_db: float = 0.0, decay_ms: int = 0, hold_ms: int = 0) -> None:
    gate = cfg["gate"]
    gate["threshold_db"] = round(max(-80.0, min(-10.0, gate["threshold_db"] + threshold_db)), 1)
    gate["decay_ms"] = clamp_int(gate["decay_ms"] + decay_ms, 10, 2000)
    gate["hold_ms"] = clamp_int(gate["hold_ms"] + hold_ms, 0, 500)


# --------------------------------------------------------------------------- #
# Purpose switching
# --------------------------------------------------------------------------- #
def _switch_purpose(cfg: dict, purpose: str) -> str:
    """Re-shape an existing config toward another purpose (delta of deltas)."""
    old = cfg["purpose"]
    if old == purpose:
        return ""
    old_map = P.PURPOSES[old]["params"]
    new_map = P.PURPOSES[purpose]["params"]
    for key in PARAM_KEYS:
        delta = int(new_map.get(key, 0)) - int(old_map.get(key, 0))
        if delta:
            _bump(cfg, key, delta)
    cap = P.PURPOSES[purpose].get("gain_cap")
    if cap is not None and cfg["params"]["gain"] > int(cap):
        cfg["params"]["gain"] = int(cap)
    gate_delta = P.PURPOSES[purpose]["gate"]
    cfg["gate"]["enabled"] = bool(gate_delta.get("enabled", cfg["gate"]["enabled"]))
    if gate_delta.get("enabled"):
        _bump_gate(cfg, float(gate_delta.get("threshold_db", 0)), int(gate_delta.get("decay_ms", 0)))
    cfg["space"].update({k: round(v, 2) for k, v in P.PURPOSES[purpose]["space"].items()})
    cfg["purpose"] = purpose
    cfg["purpose_label"] = P.PURPOSES[purpose]["label"]
    return f"Re-voiced as a {P.PURPOSES[purpose]['label'].lower()} tone: {P.PURPOSES[purpose]['note']}"


# --------------------------------------------------------------------------- #
# Instruction modifiers
# --------------------------------------------------------------------------- #
def _mod_tighter(cfg: dict) -> str:
    _bump(cfg, "bass", -5)
    _bump(cfg, "mid", 2)
    _bump_band(cfg, 100, -2.0)
    _bump_band(cfg, 200, -1.0)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] + 10, 40, 240)
    _bump_gate(cfg, threshold_db=-3.0, decay_ms=-20)
    return (
        "Tightened the low end: bass -5, 100 Hz -2 dB, high-pass moved up "
        f"to {cfg['eq']['low_cut_hz']} Hz, gate 3 dB tighter with a 20 ms faster decay."
    )


def _mod_looser(cfg: dict) -> str:
    _bump(cfg, "bass", 5)
    _bump_band(cfg, 100, 2.0)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] - 8, 40, 240)
    _bump_gate(cfg, threshold_db=3.0, decay_ms=30)
    return "Loosened the low end: bass +5, 100 Hz +2 dB, high-pass lowered, gate 3 dB more permissive."


def _mod_more_low(cfg: dict) -> str:
    _bump(cfg, "bass", 7)
    _bump_band(cfg, 100, 2.0)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] - 6, 40, 240)
    return "Added weight: bass +7, 100 Hz +2 dB, high-pass lowered 6 Hz."


def _mod_less_low(cfg: dict) -> str:
    _bump(cfg, "bass", -7)
    _bump_band(cfg, 100, -2.0)
    return "Removed low end: bass -7 and 100 Hz -2 dB."


def _mod_more_mids(cfg: dict) -> str:
    _bump(cfg, "mid", 8)
    _bump_band(cfg, 800, 2.0)
    _bump_band(cfg, 1600, 1.0)
    return "Pushed the mids: amp mid +8, +2 dB at 800 Hz, +1 dB at 1.6 kHz (better note definition in a mix)."


def _mod_less_mids(cfg: dict) -> str:
    _bump(cfg, "mid", -8)
    _bump_band(cfg, 800, -2.0)
    _bump(cfg, "treble", 2)
    return "Scooped the mids: amp mid -8, 800 Hz -2 dB, treble +2 to keep the top end alive."


def _mod_more_presence(cfg: dict) -> str:
    _bump(cfg, "presence", 8)
    _bump_band(cfg, 3200, 2.0)
    return "Added presence: presence +8 and +2 dB at 3.2 kHz, which is where pick attack lives."


def _mod_brighter(cfg: dict) -> str:
    _bump(cfg, "treble", 6)
    _bump(cfg, "presence", 4)
    return "Brightened the tone: treble +6, presence +4."


def _mod_darker(cfg: dict) -> str:
    _bump(cfg, "treble", -7)
    _bump(cfg, "presence", -5)
    cfg["eq"]["high_cut_hz"] = clamp_int(cfg["eq"]["high_cut_hz"] - 1500, 4000, 18000)
    return "Darkened the tone: treble -7, presence -5, high-cut lowered by 1.5 kHz."


def _mod_less_muddy(cfg: dict) -> str:
    _bump(cfg, "bass", -4)
    _bump(cfg, "mid", 5)
    _bump_band(cfg, 200, -2.0)
    _bump_band(cfg, 400, 1.0)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] + 8, 40, 240)
    return (
        "Cleared the mud: bass -4, 200 Hz -2 dB, 400 Hz +1 dB, high-pass +8 Hz. "
        "The 200-300 Hz region is what makes a guitar sound boxy."
    )


def _mod_more_gain(cfg: dict) -> str:
    _bump(cfg, "gain", 8)
    _bump(cfg, "presence", 2)
    return "More gain: amp gain +8 and presence +2 to keep the attack from disappearing into the saturation."


def _mod_less_gain(cfg: dict) -> str:
    _bump(cfg, "gain", -9)
    _bump(cfg, "mid", 2)
    return "Less gain: amp gain -9 and mid +2, so the reduced saturation still carries note definition."


def _mod_sustain(cfg: dict) -> str:
    _bump(cfg, "gain", 3)
    _bump_gate(cfg, decay_ms=60)
    _add_pedal(
        cfg,
        {
            "slot": "pre",
            "type": "Compressor",
            "required": False,
            "settings": {"threshold_db": -26, "ratio": 3.0, "attack_ms": 20, "release_ms": 200},
            "purpose": "Evens out sustain for legato and long held notes.",
        },
    )
    return "Added sustain: gain +3, slower gate decay (+60 ms) and a compressor in front of the amp."


def _mod_softer(cfg: dict) -> str:
    _bump(cfg, "gain", -5)
    _bump(cfg, "presence", -3)
    _bump(cfg, "treble", -2)
    return "Softened the tone: gain -5, presence -3, treble -2."


def _mod_aggressive(cfg: dict) -> str:
    _bump(cfg, "gain", 4)
    _bump(cfg, "presence", 3)
    _bump_band(cfg, 1600, 1.0)
    return "Made it more aggressive: gain +4, presence +3, +1 dB at 1.6 kHz."


def _mod_definition(cfg: dict) -> str:
    _bump(cfg, "bass", -2)
    _bump(cfg, "mid", 3)
    _bump(cfg, "presence", 3)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] + 6, 40, 240)
    return (
        "Protected note definition: bass -2, mid +3, presence +3, high-pass +6 Hz - "
        "this is the standard trade when you add weight or gain."
    )


def _mod_djent(cfg: dict) -> str:
    _bump(cfg, "bass", -5)
    _bump(cfg, "mid", 2)
    _bump(cfg, "presence", 3)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] + 18, 40, 260)
    _bump_gate(cfg, threshold_db=-4.0, decay_ms=-30)
    return "Djent-style tightening: bass -5, high-pass +18 Hz, gate 4 dB tighter, presence +3."


def _mod_stoner(cfg: dict) -> str:
    _bump(cfg, "bass", 9)
    _bump(cfg, "treble", -6)
    _bump(cfg, "gain", 4)
    cfg["eq"]["low_cut_hz"] = clamp_int(cfg["eq"]["low_cut_hz"] - 12, 40, 200)
    return "Doom/stoner voicing: bass +9, treble -6, gain +4, high-pass 12 Hz lower."


def _mod_gate_off(cfg: dict) -> str:
    cfg["gate"]["enabled"] = False
    return "Gate disabled - note tails and finger noise are now unprocessed."


def _mod_gate_on(cfg: dict) -> str:
    if cfg["gate"]["enabled"]:
        return ""
    cfg["gate"]["enabled"] = True
    return "Gate enabled."


def _mod_gate_tighter(cfg: dict) -> str:
    cfg["gate"]["enabled"] = True
    _bump_gate(cfg, threshold_db=-4.0, decay_ms=-30)
    return "Gate tightened: threshold 4 dB higher, decay 30 ms faster."


def _mod_gate_looser(cfg: dict) -> str:
    _bump_gate(cfg, threshold_db=4.0, decay_ms=40)
    return "Gate loosened: threshold 4 dB more permissive, decay 40 ms slower."


def _mod_more_reverb(cfg: dict) -> str:
    _set_space(cfg, "reverb_mix", cfg["space"]["reverb_mix"] + 0.12)
    _add_pedal(
        cfg,
        {
            "slot": "post_amp",
            "type": "Reverb",
            "required": True,
            "settings": {"decay_s": 3.0, "pre_delay_ms": 30, "mix": 0.35},
            "purpose": "Adds space behind the dry signal.",
        },
    )
    return f"More space: reverb mix now {int(cfg['space']['reverb_mix'] * 100)}%."


def _mod_less_reverb(cfg: dict) -> str:
    _set_space(cfg, "reverb_mix", cfg["space"]["reverb_mix"] - 0.10)
    return f"Drier: reverb mix now {int(cfg['space']['reverb_mix'] * 100)}%."


def _mod_more_delay(cfg: dict) -> str:
    _set_space(cfg, "delay_mix", cfg["space"]["delay_mix"] + 0.10)
    _add_pedal(
        cfg,
        {
            "slot": "post_amp",
            "type": "Delay",
            "required": True,
            "settings": {"time_ms": 400, "feedback": 0.3, "mix": 0.25},
            "purpose": "Adds depth and a rhythmic tail.",
        },
    )
    return f"More delay: delay mix now {int(cfg['space']['delay_mix'] * 100)}%."


def _mod_less_delay(cfg: dict) -> str:
    _set_space(cfg, "delay_mix", cfg["space"]["delay_mix"] - 0.10)
    return f"Less delay: delay mix now {int(cfg['space']['delay_mix'] * 100)}%."


def _mod_compression(cfg: dict) -> str:
    added = _add_pedal(
        cfg,
        {
            "slot": "pre",
            "type": "Compressor",
            "required": False,
            "settings": {"threshold_db": -28, "ratio": 4.0, "attack_ms": 12, "release_ms": 160},
            "purpose": "Adds front-end consistency and perceived sustain.",
        },
    )
    _bump(cfg, "gain", 2)
    return "Added compression in front of the amp (and +2 gain to compensate for the level loss)." if added \
        else "Compressor already present; gain +2."


MODIFIERS: list[tuple[str, tuple[str, ...], Any]] = [
    # (family, patterns, handler) - one rule per family, first match wins.
    # Order matters: gate intent first, then tone shaping, then gain.
    ("gate", (r"\b(no|without|remove|disable|off)\b[^.]{0,16}\bgate\b", r"\bgate\b[^.]{0,10}\boff\b",
              r"\bgate\b.{0,12}\b(kapat|kaldir|kaldır)"), _mod_gate_off),
    ("gate", (r"\btighter gate\b", r"\bmore gate\b", r"\bgate\b.{0,12}\bsik[iı]"), _mod_gate_tighter),
    ("gate", (r"\blooser gate\b", r"\bless gate\b", r"\bgate\b.{0,12}\bgevsek"), _mod_gate_looser),
    ("gate", (r"\bgate\b",), _mod_gate_on),

    ("tight", (r"\b(tight|tighter|tighten|tightening|siki|sikilastir)\b",), _mod_tighter),
    ("tight", (r"\b(looser|loosen|less tight|more open|gevs|gevset)\b",), _mod_looser),
    ("low", (r"\b(less|reduce|cut|lower|trim|azalt|kes)\b[^.]{0,24}\b(bass|low end|lows|bottom|bas)\b",
             r"\b(bass|low end)\b[^.]{0,10}\b(down|less)\b"), _mod_less_low),
    ("low", (r"\b(more|add|bigger|fatter|increase|boost|daha fazla|arttir|artır)\b[^.]{0,24}\b(bass|low end|lows|bottom|bas|weight)\b",
             r"\b(bigger|fatter|heavier low end)\b"), _mod_more_low),
    ("mid", (r"\b(less|reduce|scoop|scooped|cut|decrease|azalt)\b[^.]{0,24}\b(mid|mids|midrange|middle|orta)\b",
             r"\bscooped?\b"), _mod_less_mids),
    ("mid", (r"\b(more|add|increase|boost|push|daha fazla|arttir|artır)\b[^.]{0,24}\b(mid|mids|midrange|middle|orta)\b",
             r"\bmid[- ]?(boost|forward)\b"), _mod_more_mids),
    ("presence", (r"\b(more|add|increase|boost|lift)\b[^.]{0,20}\bpresence\b", r"\bpresence\b[^.]{0,10}\bup\b"),
     _mod_more_presence),
    ("bright", (r"\b(brighter|bright|more top end|more treble|parlak|tiz)\b",), _mod_brighter),
    ("dark", (r"\b(darker|darker tone|less bright|warmer|koyu|daha koyu)\b",), _mod_darker),
    ("mud", (r"\b(muddy|mud|boxy|cloudy|camurlu|çamurlu|boggy)\b", r"\bclear (it )?up\b",
             r"\bclean up the low\b"), _mod_less_muddy),
    ("sustain", (r"\b(sustain|singing|sing|legato|hold notes|sustainli)\b",), _mod_sustain),
    ("soft", (r"\b(softer|smooth|smoother|less aggressive|yumusak|yumuşak)\b",), _mod_softer),
    ("aggressive", (r"\b(more aggressive|aggressive|brutal|angrier|agresif)\b",), _mod_aggressive),
    ("definition", (r"\b(definition|defined|articulate|clarity|clearer|note separation|netlik)\b",), _mod_definition),
    ("djent", (r"\bdjent\b", r"\bdjenty\b"), _mod_djent),
    ("stoner", (r"\b(doom|stoner|sludge|fuzz)\b",), _mod_stoner),
    ("compression", (r"\b(compression|compress|squash|sikistir|sıkıştır)\b",), _mod_compression),
    ("reverb", (r"\b(more|add|bigger|increase)\b[^.]{0,20}\b(reverb|room|hall|space|ambience|wash)\b",
                r"\bmore space\b", r"\bdaha fazla reverb\b"), _mod_more_reverb),
    ("reverb", (r"\b(less|reduce|dry|drier|drier sound|az reverb)\b[^.]{0,20}\b(reverb|room|hall|ambience)\b",
                r"\bdry\b", r"\bdrier\b", r"\bdaha kuru\b"), _mod_less_reverb),
    ("delay", (r"\b(more|add|increase)\b[^.]{0,20}\b(delay|echo)\b", r"\bmore delay\b"), _mod_more_delay),
    ("delay", (r"\b(less|reduce|no|without)\b[^.]{0,20}\b(delay|echo)\b",), _mod_less_delay),
    ("gain", (r"\b(heavy|heavier|heaviest|more gain|add gain|more distortion|more drive|daha agir|daha ağır)\b",
              r"\bgain\b[^.]{0,10}\bup\b"), _mod_more_gain),
    ("gain", (r"\b(less gain|reduce (the )?gain|lower (the )?gain|cleaner|less distortion|gain azalt|dusur gain)\b",),
     _mod_less_gain),
]

_PURPOSE_TRIGGERS: tuple[tuple[str, str], ...] = (
    (r"\b(lead|solo) (tone|sound|channel)\b", "lead"),
    (r"\bfor (a )?(lead|solo)\b", "lead"),
    (r"\b(clean|sparkly) (tone|channel|sound)\b", "clean"),
    (r"\bambient (tone|version|sound)\b", "ambient"),
    (r"\brhythm (tone|version)\b", "rhythm"),
)

_NUMERIC_RE = re.compile(
    r"\b(gain|bass|mids?|midrange|treble|presence|master)\b[^0-9\n]{0,12}?(\d{1,3})\b",
    re.IGNORECASE,
)
_OFF_BY_RE = re.compile(
    r"\b(gain|bass|mids?|midrange|treble|presence|master)\b[^.\n]{0,24}?"
    r"\b(up|down|higher|lower|back|raise|reduce|increase|decrease|cut|boost|drop|trim)\b"
    r"[^.\n]{0,12}?(?:by\s+)?(\d{1,2})\b",
    re.IGNORECASE,
)
# "reduce the gain by 5" puts the verb first. The absolute rule below would otherwise read
# that as "gain = 5", which is a silent, destructive misread of a relative request.
_BY_VERB_RE = re.compile(
    r"\b(reduce|reduced|raise|raised|increase|increased|decrease|decreased|cut|drop|trim|"
    r"lower|lowered|bump|boost|boosted)\b[^.\n]{0,20}?"
    r"\b(gain|bass|mids?|midrange|treble|presence|master)\b[^.\n]{0,12}?(?:by\s+)?(\d{1,2})\b",
    re.IGNORECASE,
)
_NEGATIVE_VERBS = {"down", "lower", "lowered", "reduce", "reduced", "decrease", "decreased",
                   "cut", "drop", "trim"}
_PARAM_CANON = {
    "gain": "gain", "bass": "bass", "mid": "mid", "mids": "mid", "midrange": "mid",
    "treble": "treble", "presence": "presence", "master": "master",
}


def apply_instructions(cfg: dict, instructions: Optional[str]) -> list[str]:
    """Apply free-text modifiers + numeric overrides. Returns explanation lines."""
    explanations: list[str] = []
    text = (instructions or "").strip()
    if not text:
        return explanations
    if len(text) > 2000:
        raise ValidationError("instructions are too long (max 2000 characters)")
    folded = V_fold(text)
    # Explicit numbers are applied against the PRE-instruction values: "reduce the gain by 5"
    # must not stack on top of the "reduce" adjective (that silently gave -14 instead of -5).
    explicit_base = dict(cfg["params"])

    for pattern in _PURPOSE_TRIGGERS:
        if re.search(pattern[0], folded):
            note = _switch_purpose(cfg, pattern[1])
            if note:
                explanations.append(note)
            break

    families: set[str] = set()
    for family, patterns, handler in MODIFIERS:
        if family in families:
            continue
        if any(re.search(pattern, folded) for pattern in patterns):
            note = handler(cfg)
            if note:
                explanations.append(note)
            families.add(family)

    # Explicit numbers last: "set the amp gain to 75" beats any adjective.
    # Relative requests first ("reduce the gain by 5", "gain up 3"), then absolute ones
    # ("set gain to 80"). Anything a relative rule consumed is skipped by the absolute rule.
    consumed: list[tuple[int, int]] = []
    for match in _OFF_BY_RE.finditer(folded):
        param = _PARAM_CANON[match.group(1).casefold()]
        direction = -1 if match.group(2).casefold() in _NEGATIVE_VERBS else 1
        base = explicit_base.get(param, cfg["params"][param])
        cfg["params"][param] = clamp_int(base + direction * int(match.group(3)), 0, 100)
        explanations.append(
            f"{PARAM_LABELS[param]} {base} -> {cfg['params'][param]} (explicit {direction * int(match.group(3)):+d})."
        )
        consumed.append(match.span())

    for match in _BY_VERB_RE.finditer(folded):
        if any(s <= match.start() < e for s, e in consumed):
            continue
        direction = -1 if match.group(1).casefold() in _NEGATIVE_VERBS else 1
        param = _PARAM_CANON[match.group(2).casefold()]
        base = explicit_base.get(param, cfg["params"][param])
        cfg["params"][param] = clamp_int(base + direction * int(match.group(3)), 0, 100)
        explanations.append(
            f"{PARAM_LABELS[param]} {base} -> {cfg['params'][param]} (explicit {direction * int(match.group(3)):+d})."
        )
        consumed.append(match.span())

    for match in _NUMERIC_RE.finditer(folded):
        if any(s <= match.start() < e for s, e in consumed):
            continue
        param = _PARAM_CANON[match.group(1).casefold()]
        value = int(match.group(2))
        if value > 100:
            explanations.append(
                f"Ignored {param} = {value}: ToneForge parameters are normalised 0-100, "
                "so this would be out of range."
            )
            continue
        previous = cfg["params"][param]
        cfg["params"][param] = clamp_int(value, 0, 100)
        explanations.append(f"Set {PARAM_LABELS[param].lower()} to {cfg['params'][param]} (was {previous}).")

    return explanations


# --------------------------------------------------------------------------- #
# Signal chain rendering
# --------------------------------------------------------------------------- #
def _gate_text(gate: dict) -> str:
    return (
        f"threshold {gate['threshold_db']} dB, decay {gate['decay_ms']} ms, "
        f"hold {gate['hold_ms']} ms"
    )


def _pedal_by_family(pedals: Iterable[dict], *needles: str) -> Optional[dict]:
    for pedal in pedals:
        haystack = pedal["type"].casefold()
        if any(needle in haystack for needle in needles):
            return pedal
    return None


def _pedal_summary(pedal: dict) -> str:
    parts = [f"{key} {value}" for key, value in pedal["settings"].items()]
    return ", ".join(parts)


def render_signal_chain(cfg: dict) -> list[dict]:
    """Render the ordered signal chain from the config's blocks."""
    chain: list[dict] = []
    pedals = cfg["pedals"]

    for entry in P.CHAIN_ORDER:
        key = entry["key"]
        item: Optional[dict] = None

        if key == "noise_gate":
            if cfg["gate"]["enabled"]:
                item = {
                    "stage": entry["role"],
                    "component": "Noise gate",
                    "settings": _gate_text(cfg["gate"]),
                    "notes": "First in the chain, before any gain stage.",
                }
        elif key == "boost":
            pedal = _pedal_by_family(pedals, "overdrive", "boost", "fuzz", "distortion")
            if pedal:
                item = {
                    "stage": entry["role"],
                    "component": pedal["type"],
                    "settings": _pedal_summary(pedal),
                    "notes": pedal["purpose"],
                }
        elif key == "compressor":
            pedal = _pedal_by_family(pedals, "compressor", "comp")
            if pedal:
                item = {
                    "stage": entry["role"],
                    "component": pedal["type"],
                    "settings": _pedal_summary(pedal),
                    "notes": pedal["purpose"],
                }
        elif key == "amp":
            item = {
                "stage": entry["role"],
                "component": cfg["amp"]["category"],
                "settings": (
                    f"gain {cfg['params']['gain']}, bass {cfg['params']['bass']}, "
                    f"mid {cfg['params']['mid']}, treble {cfg['params']['treble']}, "
                    f"presence {cfg['params']['presence']}, master {cfg['params']['master']}"
                ),
                "notes": f"{cfg['amp']['family']} - {cfg['amp']['character']}",
            }
        elif key == "cabinet":
            item = {
                "stage": entry["role"],
                "component": f"{cfg['cabinet']['configuration']} / {cfg['cabinet']['speaker_character']}",
                "settings": (
                    f"{cfg['mic']['family']}, {cfg['mic']['position']}"
                ),
                "notes": cfg["mic"]["note"],
            }
        elif key == "post_eq":
            bands = ", ".join(f"{band['hz']} Hz {band['db']:+g} dB" for band in cfg["eq"]["bands"])
            item = {
                "stage": entry["role"],
                "component": "Graphic EQ (7-band)",
                "settings": (
                    f"high-pass {cfg['eq']['low_cut_hz']} Hz, low-pass {cfg['eq']['high_cut_hz']} Hz; "
                    + bands
                ),
                "notes": "After the cab: EQ here shapes the recorded tone, not the amp's feel.",
            }
        elif key == "modulation":
            pedal = _pedal_by_family(pedals, "chorus", "flanger", "phaser", "modulation")
            if pedal:
                item = {
                    "stage": entry["role"],
                    "component": pedal["type"],
                    "settings": _pedal_summary(pedal),
                    "notes": pedal["purpose"],
                }
        elif key == "delay":
            pedal = _pedal_by_family(pedals, "delay", "echo")
            if pedal:
                item = {
                    "stage": entry["role"],
                    "component": pedal["type"],
                    "settings": _pedal_summary(pedal),
                    "notes": pedal["purpose"],
                }
            elif cfg["space"]["delay_mix"] > 0.02:
                item = {
                    "stage": entry["role"],
                    "component": "Delay (post-amp)",
                    "settings": f"mix {int(cfg['space']['delay_mix'] * 100)}%",
                    "notes": "Subtle depth rather than an audible effect.",
                }
        elif key == "reverb":
            pedal = _pedal_by_family(pedals, "reverb", "hall", "plate")
            if pedal:
                item = {
                    "stage": entry["role"],
                    "component": pedal["type"],
                    "settings": _pedal_summary(pedal),
                    "notes": pedal["purpose"],
                }
            elif cfg["space"]["reverb_mix"] > 0.02:
                item = {
                    "stage": entry["role"],
                    "component": "Reverb (post-amp)",
                    "settings": f"mix {int(cfg['space']['reverb_mix'] * 100)}%",
                    "notes": "Short room, low mix: adds a sense of a real room.",
                }

        if item is not None:
            item["order"] = len(chain) + 1
            item["apply_in_amplitube"] = "manual"
            chain.append(item)

    return chain


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #
def _apply_tuning(cfg: dict, tuning: str) -> None:
    spec = P.TUNINGS[tuning]
    cfg["tuning"] = tuning
    cfg["tuning_label"] = spec["label"]
    cfg["tuning_note"] = spec["note"]
    _bump(cfg, "bass", -int(spec["bass_trim"]))
    _bump(cfg, "presence", int(spec["presence_trim"]))
    cfg["eq"]["low_cut_hz"] = spec["low_cut_hz"]
    if cfg["gate"]["enabled"]:
        _bump_gate(cfg, threshold_db=-float(spec["gate_trim_db"]))


def _apply_pickup(cfg: dict, pickup: str) -> None:
    spec = P.PICKUPS[pickup]
    cfg["pickup"] = pickup
    cfg["pickup_label"] = spec["label"]
    cfg["pickup_note"] = spec["note"]
    _bump(cfg, "gain", int(spec["gain_bias"]))
    _bump(cfg, "treble", int(spec["treble_bias"]))
    _bump(cfg, "bass", int(spec["bass_bias"]))
    if spec["noise"] == "high" and cfg["gate"]["enabled"]:
        _bump_gate(cfg, threshold_db=-3.0)


def _apply_purpose(cfg: dict, purpose: str) -> None:
    spec = P.PURPOSES[purpose]
    cfg["purpose"] = purpose
    cfg["purpose_label"] = spec["label"]
    cfg["purpose_note"] = spec["note"]
    for key, delta in spec["params"].items():
        _bump(cfg, key, int(delta))
    cap = spec.get("gain_cap")
    if cap is not None and cfg["params"]["gain"] > int(cap):
        cfg["params"]["gain"] = int(cap)
        cfg["purpose_note"] += f" Gain capped at {int(cap)} so the amp stays in this register."
    gate = spec["gate"]
    if "enabled" in gate:
        cfg["gate"]["enabled"] = bool(gate["enabled"])
    if cfg["gate"]["enabled"]:
        _bump_gate(cfg, float(gate.get("threshold_db", 0)), int(gate.get("decay_ms", 0)))
    cfg["space"] = dict(spec["space"])


def _sync_gate_pedal(cfg: dict) -> None:
    """Keep the pedal list honest about the gate's real state.

    A profile ships a gate pedal, but a purpose (clean/ambient/crunch) or a
    "remove the gate" instruction can switch the gate off. Leaving the pedal in
    the list would contradict `gate.enabled` and the rendered chain.
    """
    has_gate_pedal = any("gate" in pedal["type"].casefold() for pedal in cfg["pedals"])
    if not cfg["gate"]["enabled"]:
        cfg["pedals"] = [p for p in cfg["pedals"] if "gate" not in p["type"].casefold()]
        return
    gate_settings = {
        "threshold_db": cfg["gate"]["threshold_db"],
        "decay_ms": cfg["gate"]["decay_ms"],
        "hold_ms": cfg["gate"]["hold_ms"],
    }
    if has_gate_pedal:
        for pedal in cfg["pedals"]:
            if "gate" in pedal["type"].casefold():
                pedal["settings"] = dict(gate_settings)
        return
    cfg["pedals"].insert(
        0,
        {
            "slot": "pre",
            "type": "Noise gate",
            "required": True,
            "settings": gate_settings,
            "purpose": "Silences the idle hiss of a high-gain channel between phrases.",
        },
    )


def _default_name(profile: dict, tuning: str, purpose: str) -> str:
    return f"{profile['label']} - {P.TUNINGS[tuning]['label'].split(' (')[0]} ({P.PURPOSES[purpose]['label'].lower()})"


def build_tone(
    *,
    genre: Optional[str] = None,
    reference: Optional[str] = None,
    tuning: Optional[str] = None,
    pickup: Optional[str] = None,
    purpose: Optional[str] = None,
    gain_level: Optional[int] = None,
    instructions: Optional[str] = None,
    name: Optional[str] = None,
) -> dict[str, Any]:
    """Build a complete tone configuration from a natural-language-ish request."""
    genre = require_text(genre, "genre", max_len=120)
    reference = require_text(reference, "reference", max_len=120)
    instructions = require_text(instructions, "instructions", max_len=2000)

    profile_key, assumptions = resolve_genre(genre, reference)
    profile = P.PROFILES[profile_key]

    tuning_key = normalize_choice(tuning, "tuning", P.TUNING_ALIASES, default=profile["default_tuning"])
    if tuning is None:
        assumptions.append(
            f"No tuning given; used {P.TUNINGS[tuning_key]['label']} (the {profile['label']} default). "
            "Say e.g. 'drop C' to change it."
        )

    pickup_key = None
    if pickup is not None:
        pickup_key = normalize_choice(pickup, "pickup", P.PICKUP_ALIASES)
    else:
        pickup_key = "humbucker"
        assumptions.append("No pickup given; assumed a passive humbucker.")

    purpose_key = normalize_choice(purpose, "purpose", P.PURPOSE_ALIASES, default=profile["default_purpose"])

    if gain_level is not None:
        gain_level = int(gain_level)  # type: ignore[arg-type]
        if not 0 <= gain_level <= 100:
            raise ValidationError("gain_level must be between 0 and 100")

    cfg: dict[str, Any] = {
        "genre": profile_key,
        "genre_label": profile["label"],
        "reference": reference,
        "amp": dict(profile["amp"]),
        "cabinet": dict(profile["cabinet"]),
        "mic": dict(profile["mic"]),
        "params": dict(profile["params"]),
        "eq": {
            "low_cut_hz": profile["eq"]["low_cut_hz"],
            "high_cut_hz": profile["eq"]["high_cut_hz"],
            "bands": [dict(band) for band in profile["eq"]["bands"]],
        },
        "gate": dict(profile["gate"]),
        "pedals": [
            {**pedal, "settings": dict(pedal["settings"])} for pedal in profile["pedals"]
        ],
        "space": {},
        "why": list(profile["why"]),
        "post": list(profile["post"]),
    }

    _apply_tuning(cfg, tuning_key)
    _apply_pickup(cfg, pickup_key)
    _apply_purpose(cfg, purpose_key)

    if gain_level is not None:
        before = cfg["params"]["gain"]
        cfg["params"]["gain"] = gain_level
        cfg["why"].insert(
            0, f"Gain set to {gain_level} as requested (profile starting point was {before})."
        )

    instruction_notes = apply_instructions(cfg, instructions)
    _sync_gate_pedal(cfg)
    if instruction_notes:
        cfg["why"].insert(
            0,
            "Your extra instructions moved some starting values; the profile rationale below describes "
            "the starting point, and toneforge_adjust_preset reports exact before/after changes.",
        )

    cfg["signal_chain"] = render_signal_chain(cfg)
    cfg["instructions_applied"] = instruction_notes
    if cfg.get("purpose_note"):
        cfg["why"].append(f"Purpose ({cfg['purpose_label']}): {cfg['purpose_note']}")
    cfg["assumptions"] = assumptions
    cfg["disclaimer"] = P.DISCLAIMER
    cfg["name"] = name or _default_name(profile, tuning_key, purpose_key)
    cfg["description"] = _describe(cfg)
    return cfg


def _describe(cfg: dict) -> str:
    bits = [
        f"{cfg['genre_label']} {cfg['purpose_label'].lower()} tone",
        cfg["tuning_label"],
        cfg["pickup_label"],
    ]
    if cfg.get("reference"):
        bits.insert(1, f"inspired by {cfg['reference']}")
    return " | ".join(bits)


# --------------------------------------------------------------------------- #
# Adjust
# --------------------------------------------------------------------------- #
def _snapshot(cfg: dict) -> dict:
    return {
        "params": dict(cfg["params"]),
        "gate": dict(cfg["gate"]),
        "eq": {
            "low_cut_hz": cfg["eq"]["low_cut_hz"],
            "high_cut_hz": cfg["eq"]["high_cut_hz"],
            "bands": [dict(band) for band in cfg["eq"]["bands"]],
        },
        "pedals": [pedal["type"] for pedal in cfg["pedals"]],
        "space": dict(cfg["space"]),
        "purpose": cfg["purpose"],
    }


def _diff(before: dict, after: dict) -> list[dict]:
    changes: list[dict] = []
    for key, value in before["params"].items():
        if after["params"].get(key) != value:
            changes.append({"field": f"params.{key}", "before": value, "after": after["params"][key]})
    for key, value in before["gate"].items():
        if after["gate"].get(key) != value:
            changes.append({"field": f"gate.{key}", "before": value, "after": after["gate"][key]})
    if before["eq"]["low_cut_hz"] != after["eq"]["low_cut_hz"]:
        changes.append({
            "field": "eq.low_cut_hz",
            "before": before["eq"]["low_cut_hz"],
            "after": after["eq"]["low_cut_hz"],
        })
    if before["eq"]["high_cut_hz"] != after["eq"]["high_cut_hz"]:
        changes.append({
            "field": "eq.high_cut_hz",
            "before": before["eq"]["high_cut_hz"],
            "after": after["eq"]["high_cut_hz"],
        })
    before_bands = {band["hz"]: band["db"] for band in before["eq"]["bands"]}
    after_bands = {band["hz"]: band["db"] for band in after["eq"]["bands"]}
    for hz in sorted(set(before_bands) | set(after_bands)):
        if before_bands.get(hz) != after_bands.get(hz):
            changes.append({
                "field": f"eq.{hz}hz",
                "before": before_bands.get(hz),
                "after": after_bands.get(hz),
            })
    if before["pedals"] != after["pedals"]:
        changes.append({
            "field": "pedals",
            "before": before["pedals"],
            "after": after["pedals"],
        })
    for key in ("delay_mix", "reverb_mix"):
        if before["space"].get(key) != after["space"].get(key):
            changes.append({
                "field": f"space.{key}",
                "before": before["space"].get(key),
                "after": after["space"].get(key),
            })
    if before["purpose"] != after["purpose"]:
        changes.append({"field": "purpose", "before": before["purpose"], "after": after["purpose"]})
    return changes


def adjust_tone(
    cfg: dict,
    instructions: str,
    *,
    gain_level: Optional[int] = None,
    purpose: Optional[str] = None,
    tuning: Optional[str] = None,
) -> tuple[dict, list[dict], list[str]]:
    """Return (updated_config, changes, explanations) without touching the stored preset."""
    instructions = require_text(instructions, "instructions", max_len=2000, required=True) or ""
    working = _deep_copy(cfg)
    before = _snapshot(working)
    explanations: list[str] = []

    if tuning:
        tuning_key = normalize_choice(tuning, "tuning", P.TUNING_ALIASES)
        _apply_tuning(working, tuning_key)
        explanations.append(f"Re-tuned the recipe for {P.TUNINGS[tuning_key]['label']}.")
    if purpose:
        purpose_key = normalize_choice(purpose, "purpose", P.PURPOSE_ALIASES)
        note = _switch_purpose(working, purpose_key)
        if note:
            explanations.append(note)
    if gain_level is not None:
        level = int(gain_level)
        if not 0 <= level <= 100:
            raise ValidationError("gain_level must be between 0 and 100")
        working["params"]["gain"] = level
        explanations.append(f"Gain set to {level}.")

    explanations.extend(apply_instructions(working, instructions))
    _sync_gate_pedal(working)

    if not explanations:
        explanations.append(
            "No recognised adjustment in that instruction. Nothing changed. "
            "Try phrasing like 'tighter low end', 'more mids', 'less gain', 'add presence', "
            "'less muddy' or 'set gain to 75'."
        )

    working["signal_chain"] = render_signal_chain(working)
    working["instructions_applied"] = list(working.get("instructions_applied", [])) + explanations
    working["description"] = _describe(working)
    changes = _diff(before, _snapshot(working))
    return working, changes, explanations


def _deep_copy(value: Any) -> Any:
    import copy

    return copy.deepcopy(value)


def describe_changes(changes: list[dict]) -> str:
    """One-line human summary of a change list."""
    if not changes:
        return "no parameter changed"
    return ", ".join(f"{item['field']} {item['before']}->{item['after']}" for item in changes)


# --------------------------------------------------------------------------- #
# Reference-audio overrides
# --------------------------------------------------------------------------- #
def apply_overrides(cfg: dict, overrides: dict, *, source: str = "reference audio") -> dict:
    """Write measured overrides (params/eq/gate/space) into an existing tone config.

    Deliberately additive: the profile still owns the amp/cab/pedal *families*, while
    the numbers come from the recording. Every applied value keeps its reason.
    """
    params = overrides.get("params") or {}
    for key in ("gain", "bass", "mid", "treble", "presence", "master"):
        if key in params:
            cfg["params"][key] = int(params[key])

    eq = overrides.get("eq") or {}
    if "low_cut_hz" in eq:
        cfg["eq"]["low_cut_hz"] = int(eq["low_cut_hz"])
    if "high_cut_hz" in eq:
        cfg["eq"]["high_cut_hz"] = int(eq["high_cut_hz"])
    for band in eq.get("bands") or []:
        for target in cfg["eq"]["bands"]:
            if int(target["hz"]) == int(band["hz"]):
                target["db"] = band["db"]

    gate = overrides.get("gate") or {}
    for key in ("enabled", "threshold_db", "decay_ms", "hold_ms"):
        if key in gate:
            cfg["gate"][key] = gate[key]

    space = overrides.get("space") or {}
    for key in ("delay_mix", "reverb_mix"):
        if key in space:
            cfg["space"][key] = space[key]

    if overrides.get("amp"):
        cfg["amp"] = dict(overrides["amp"])
    if overrides.get("cabinet"):
        cfg["cabinet"] = dict(overrides["cabinet"])

    _sync_gate_pedal(cfg)
    for pedal in cfg["pedals"]:
        lowered = pedal["type"].casefold()
        if "reverb" in lowered and "reverb_mix" in space:
            pedal["settings"]["mix"] = round(float(space["reverb_mix"]), 3)
        elif "delay" in lowered and "delay_mix" in space:
            pedal["settings"]["mix"] = round(float(space["delay_mix"]), 3)

    measured = [f"Measured against {source}: {line}" for line in (overrides.get("why") or [])]
    if overrides.get("amp"):
        families = (
            "Amp and cabinet families were chosen from the measured brightness; pedal layout and tuning "
            f"structure come from the '{cfg.get('genre_label', 'profile')}' profile. Numeric settings were "
            "measured from the recording."
        )
    else:
        families = (
            f"Amp, cabinet and pedal families come from the '{cfg.get('genre_label', 'profile')}' profile; "
            "every numeric setting here was measured from the recording."
        )
    cfg["why"] = measured + [families]
    cfg["signal_chain"] = render_signal_chain(cfg)
    cfg["description"] = _describe(cfg)
    cfg["reference_analysis"] = {
        "source": source,
        "params": dict(cfg["params"]),
        "eq": {
            "low_cut_hz": cfg["eq"]["low_cut_hz"],
            "high_cut_hz": cfg["eq"]["high_cut_hz"],
            "bands": [dict(band) for band in cfg["eq"]["bands"]],
        },
        "gate": dict(cfg["gate"]),
        "space": dict(cfg["space"]),
        "caveats": list(overrides.get("caveats") or []),
    }
    return cfg
