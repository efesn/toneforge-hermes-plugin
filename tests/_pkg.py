"""Load the plugin directory exactly the way Hermes does: as a package.

The loader imports ``__init__.py`` with ``submodule_search_locations`` pointing at
the plugin root, which is what makes the sibling modules importable through
relative imports. Mirroring that here means the tests exercise the real import
shape instead of a sys.path hack that could hide a broken relative import.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "toneforge_plugin"

if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE, ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    if spec is None or spec.loader is None:  # pragma: no cover - broken checkout
        raise RuntimeError(f"cannot load the ToneForge package from {ROOT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)

plugin = sys.modules[PACKAGE]

from toneforge_plugin import (  # noqa: E402  (import after the package exists)
    midi_io,
    midi_map,
    preset_store,
    reference_analysis,
    schemas,
    tone_engine,
    tone_profiles,
    tools,
    validation,
)

__all__ = [
    "plugin",
    "midi_io",
    "midi_map",
    "preset_store",
    "reference_analysis",
    "schemas",
    "tone_engine",
    "tone_profiles",
    "tools",
    "validation",
]
