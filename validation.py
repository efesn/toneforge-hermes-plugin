"""Input validation for ToneForge.

Every user-supplied value passes through this module before it reaches the tone
engine, the preset store or the MIDI bridge. The rules are deliberately strict:
a rejected value produces an actionable message, never a silently clamped one,
except where clamping is explicitly the documented behaviour (tone parameters).
"""

from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Iterable, Mapping, Optional


class ToneForgeError(ValueError):
    """Base class for every error ToneForge raises on purpose."""


class ValidationError(ToneForgeError):
    """A caller-supplied value was rejected."""


class NotFoundError(ToneForgeError):
    """A named preset, mapping or port does not exist."""


class ConflictError(ToneForgeError):
    """An operation would overwrite or clobber existing data."""


MAX_TEXT = 280
MAX_INSTRUCTIONS = 2000

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_MAPPING_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


def coerce_int(
    value: Any,
    field: str,
    *,
    lo: Optional[int] = None,
    hi: Optional[int] = None,
    default: Optional[int] = None,
    allow_none: bool = True,
) -> Optional[int]:
    """Return *value* as an int in [lo, hi].

    Accepts ints and integral floats/strings (``75``, ``75.0``, ``"75"``).
    Rejects bools, NaN/inf, fractions and out-of-range values.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not None or allow_none:
            return default
        raise ValidationError(f"{field} is required")

    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number, not a boolean")

    number: float
    if isinstance(value, int):
        number = float(value)
    elif isinstance(value, float):
        number = value
    elif isinstance(value, str):
        text = value.strip()
        try:
            number = float(text)
        except ValueError:
            raise ValidationError(f"{field} must be a whole number, got {value!r}") from None
    else:
        raise ValidationError(f"{field} must be a number, got {type(value).__name__}")

    if math.isnan(number) or math.isinf(number):
        raise ValidationError(f"{field} must be a finite number")
    if number != int(number):
        raise ValidationError(f"{field} must be a whole number, got {number}")
    result = int(number)
    if lo is not None and result < lo:
        raise ValidationError(f"{field} must be >= {lo}, got {result}")
    if hi is not None and result > hi:
        raise ValidationError(f"{field} must be <= {hi}, got {result}")
    return result


def coerce_float(
    value: Any,
    field: str,
    *,
    lo: Optional[float] = None,
    hi: Optional[float] = None,
    default: Optional[float] = None,
) -> Optional[float]:
    """Return *value* as a finite float in [lo, hi]."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    if isinstance(value, bool):
        raise ValidationError(f"{field} must be a number, not a boolean")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be a number, got {value!r}") from None
    if math.isnan(number) or math.isinf(number):
        raise ValidationError(f"{field} must be a finite number")
    if lo is not None and number < lo:
        raise ValidationError(f"{field} must be >= {lo}, got {number}")
    if hi is not None and number > hi:
        raise ValidationError(f"{field} must be <= {hi}, got {number}")
    return number


def clamp_int(value: int, lo: int, hi: int) -> int:
    """Clamp an already-validated integer into [lo, hi]."""
    return max(lo, min(hi, int(value)))


def require_text(
    value: Any,
    field: str,
    *,
    max_len: int = MAX_TEXT,
    default: Optional[str] = None,
    required: bool = False,
) -> Optional[str]:
    """Return a trimmed, length-limited string (or *default* when absent)."""
    if value is None:
        if required:
            raise ValidationError(f"{field} is required")
        return default
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text, got {type(value).__name__}")
    text = value.strip()
    if not text:
        if required:
            raise ValidationError(f"{field} must not be empty")
        return default
    if len(text) > max_len:
        raise ValidationError(f"{field} is too long (max {max_len} characters)")
    # Reject control characters that would corrupt JSON logs or terminal output.
    if any(ord(ch) < 32 and ch not in "\t\n" for ch in text):
        raise ValidationError(f"{field} contains control characters")
    return text


def normalize_choice(
    value: Any,
    field: str,
    choices: Mapping[str, str],
    *,
    default: Optional[str] = None,
) -> str:
    """Resolve *value* against a {alias: canonical} table, case/space-insensitively."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not None:
            return default
        raise ValidationError(f"{field} is required (one of: {', '.join(sorted(set(choices.values())))})")
    if not isinstance(value, str):
        raise ValidationError(f"{field} must be text, got {type(value).__name__}")
    key = _fold(value)
    if key in choices:
        return choices[key]
    # Tolerate "modern-metal" / "modern metal " spellings.
    squashed = re.sub(r"[\s_-]+", "", key)
    for alias, canonical in choices.items():
        if re.sub(r"[\s_-]+", "", alias) == squashed:
            return canonical
    raise ValidationError(
        f"{field} {value!r} is not recognised; choose one of: "
        + ", ".join(sorted(set(choices.values())))
    )


def _fold(text: str) -> str:
    """Lowercase + strip accents so 'Sıkı' and 'siki' compare equal."""
    decomposed = unicodedata.normalize("NFKD", text.strip().casefold())
    asciiish = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # Turkish dotless i has no NFKD decomposition, so map it explicitly.
    asciiish = asciiish.replace("\u0131", "i")
    return re.sub(r"\s+", " ", asciiish.strip())


def slugify(name: str, *, fallback: str = "preset") -> str:
    """Convert a display name into a safe file stem.

    ``"Rammstein — Sonne (Drop D)!"`` -> ``"rammstein-sonne-drop-d"``.
    """
    if not isinstance(name, str):
        raise ValidationError("preset name must be text")
    folded = _fold(name)
    # Turkish dotless i survives casefold as 'i' after NFKD in practice; map the rest.
    folded = folded.replace("\u0131", "i")
    ascii_slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    ascii_slug = re.sub(r"-{2,}", "-", ascii_slug)[:64].strip("-")
    if not ascii_slug:
        ascii_slug = fallback
    if not _SLUG_RE.match(ascii_slug):
        raise ValidationError(f"cannot derive a safe file name from {name!r}")
    return ascii_slug


def validate_slug(slug: str) -> str:
    """Validate an already-computed preset slug (defence in depth before touching disk)."""
    if not isinstance(slug, str) or not _SLUG_RE.match(slug):
        raise ValidationError(
            "preset name must contain only letters, digits, dots, dashes and underscores "
            "(max 64 characters, must start with a letter or digit)"
        )
    if ".." in slug or slug.startswith("."):
        raise ValidationError("preset name must not contain '..' or start with '.'")
    return slug


def validate_mapping_name(name: str) -> str:
    """Mapping keys are lowercase identifiers such as ``amp_gain``."""
    if not isinstance(name, str):
        raise ValidationError("mapping name must be text")
    candidate = _fold(name).replace(" ", "_")
    if not _MAPPING_NAME_RE.match(candidate):
        raise ValidationError(
            "mapping name must be a lowercase identifier (a-z, 0-9, underscore; max 32 characters)"
        )
    return candidate


def ensure_mapping(value: Any, field: str) -> dict:
    """Require a JSON object where a JSON object is expected."""
    if not isinstance(value, dict):
        raise ValidationError(f"{field} must be an object, got {type(value).__name__}")
    return value


def ensure_list(value: Any, field: str) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    raise ValidationError(f"{field} must be a list, got {type(value).__name__}")


def dedupe(items: Iterable[str]) -> list:
    """Order-preserving de-duplication."""
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def fold(text: str) -> str:
    """Public alias for the accent-insensitive folding used across the plugin."""
    return _fold(text)
