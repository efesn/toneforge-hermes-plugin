"""Preset library: JSON files in a per-profile data directory.

Storage rules
-------------
* A preset is a JSON document, never a native AmpliTube ``.at5p`` file.
* File names are derived with :func:`validation.slugify` and re-validated before
  any path is built, so ``..``, absolute paths, drive letters and separators can
  never reach ``open()``.
* Writes are atomic (temp file in the same directory + ``os.replace``), so a
  crash cannot leave a half-written preset behind.
* Overwriting is opt-in: ``save(overwrite=True)`` is the only way to replace an
  existing preset, and it bumps the stored version.
"""

from __future__ import annotations

import json
import pathlib
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import validation as V

try:  # Hermes runtime; absent when the module is imported by the test runner.
    from plugins.plugin_storage import plugin_data_dir as _plugin_data_dir
except Exception:  # pragma: no cover - exercised only outside Hermes
    _plugin_data_dir = None

PLUGIN_NAME = "tone-forge"
SCHEMA_VERSION = 1
def _plugin_version() -> str:
    """Read the version from plugin.yaml so records cannot drift from the manifest."""
    try:
        manifest = pathlib.Path(__file__).with_name("plugin.yaml")
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if line.startswith("version:"):
                value = line.split(":", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    except OSError:
        pass
    return "1.1.2"


PLUGIN_VERSION = _plugin_version()
MAX_FILE_BYTES = 1_000_000


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def data_dir() -> Path:
    """Resolve the writable data directory.

    Precedence: ``TONEFORGE_DATA_DIR`` (tests, portable installs) -> Hermes
    ``plugin_data_dir`` -> ``$HERMES_HOME/plugin-data/tone-forge`` ->
    ``~/.hermes/plugin-data/tone-forge``.

    The ``HERMES_HOME`` step matters for scripts that run *outside* a Hermes
    process (the copied plugin cannot import ``plugins.plugin_storage``): without
    it a CLI script would write to ``~/.hermes`` while the running agent reads
    ``$HERMES_HOME``, and the mapping would silently not exist for the agent.
    """
    override = os.environ.get("TONEFORGE_DATA_DIR")
    if override:
        root = Path(override).expanduser()
    elif _plugin_data_dir is not None:
        root = _plugin_data_dir(PLUGIN_NAME)
    elif os.environ.get("HERMES_HOME"):
        root = Path(os.environ["HERMES_HOME"]).expanduser() / "plugin-data" / PLUGIN_NAME
    else:
        root = Path.home() / ".hermes" / "plugin-data" / PLUGIN_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


class PresetStore:
    """A directory of JSON presets, addressed by slug."""

    def __init__(self, root: Optional[Path] = None) -> None:
        self.root = Path(root) if root is not None else data_dir() / "presets"
        self.root.mkdir(parents=True, exist_ok=True)

    # -- path helpers ------------------------------------------------------ #
    def path_for(self, slug: str) -> Path:
        safe = V.validate_slug(slug)
        candidate = (self.root / f"{safe}.json").resolve()
        root = self.root.resolve()
        if candidate.parent != root:
            raise V.ValidationError("resolved preset path escapes the preset directory")
        return candidate

    def exists(self, slug: str) -> bool:
        return self.path_for(slug).exists()

    # -- write ------------------------------------------------------------- #
    def save(
        self,
        config: dict[str, Any],
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        notes: Optional[list[str]] = None,
        overwrite: bool = False,
        slug: Optional[str] = None,
    ) -> dict[str, Any]:
        display_name = V.require_text(name or config.get("name"), "preset name", max_len=80, required=True)
        assert display_name is not None
        preset_slug = V.validate_slug(slug) if slug else V.slugify(display_name)
        path = self.path_for(preset_slug)
        now = utc_now()

        existing: Optional[dict[str, Any]] = None
        if path.exists():
            if not overwrite:
                existing = self._read(path)
                raise V.ConflictError(
                    f"A preset named {preset_slug!r} already exists "
                    f"(version {existing.get('version', 1)}, updated {existing.get('updated_at', '?')}). "
                    "Pass overwrite=true to replace it, or choose another name."
                )
            existing = self._read(path)

        record: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "slug": preset_slug,
            "name": display_name,
            "description": description or config.get("description", ""),
            "genre": config.get("genre"),
            "genre_label": config.get("genre_label"),
            "reference": config.get("reference"),
            "tuning": config.get("tuning"),
            "tuning_label": config.get("tuning_label"),
            "pickup": config.get("pickup"),
            "purpose": config.get("purpose"),
            "purpose_label": config.get("purpose_label"),
            "notes": list(notes or []),
            "config": config,
            "version": int(existing.get("version", 0)) + 1 if existing else 1,
            "created_at": existing.get("created_at", now) if existing else now,
            "updated_at": now,
            "created_by": {"plugin": PLUGIN_NAME, "plugin_version": PLUGIN_VERSION},
            "disclaimer": config.get("disclaimer"),
        }
        self._write_atomic(path, record)
        return record

    # -- read -------------------------------------------------------------- #
    def load(self, identifier: str) -> dict[str, Any]:
        path = self._resolve(identifier)
        return self._read(path)

    def list(self) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                record = self._read(path)
            except V.ToneForgeError:
                continue
            summaries.append(
                {
                    "slug": record.get("slug", path.stem),
                    "name": record.get("name", path.stem),
                    "description": record.get("description", ""),
                    "genre": record.get("genre_label") or record.get("genre"),
                    "tuning": record.get("tuning_label") or record.get("tuning"),
                    "purpose": record.get("purpose_label") or record.get("purpose"),
                    "version": record.get("version", 1),
                    "updated_at": record.get("updated_at"),
                }
            )
        summaries.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
        return summaries

    def delete(self, identifier: str, *, confirm: bool = False) -> dict[str, Any]:
        if confirm is not True:
            raise V.ValidationError(
                "delete requires confirm=true: removing a preset cannot be undone"
            )
        path = self._resolve(identifier)
        record = self._read(path)
        path.unlink()
        return {"slug": record.get("slug", path.stem), "name": record.get("name", path.stem)}

    # -- internals --------------------------------------------------------- #
    def _resolve(self, identifier: str) -> Path:
        """Accept a slug, a display name or a case-insensitive fragment match."""
        text = V.require_text(identifier, "preset", max_len=120, required=True)
        assert text is not None
        try:
            path = self.path_for(V.slugify(text))
            if path.exists():
                return path
        except V.ValidationError:
            pass

        folded = V._fold(text)
        for candidate in self.root.glob("*.json"):
            if candidate.stem == folded:
                return candidate
        matches = []
        for candidate in self.root.glob("*.json"):
            try:
                record = self._read(candidate)
            except V.ToneForgeError:
                continue
            haystack = V._fold(f"{record.get('name', '')} {record.get('slug', '')}")
            if folded in haystack:
                matches.append(candidate)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(sorted(path.stem for path in matches))
            raise V.ValidationError(
                f"{identifier!r} matches several presets ({names}); use the exact slug"
            )
        raise V.NotFoundError(f"No preset named {identifier!r}. Use toneforge_list_presets to see what exists.")

    def _read(self, path: Path) -> dict[str, Any]:
        try:
            stat = path.stat()
        except OSError as exc:
            raise V.NotFoundError(f"preset file is not readable: {exc}") from None
        if stat.st_size > MAX_FILE_BYTES:
            raise V.ToneForgeError(f"preset file {path.name} is unexpectedly large; refusing to load it")
        try:
            with path.open("r", encoding="utf-8") as handle:
                record = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise V.ToneForgeError(f"preset file {path.name} is not valid JSON: {exc}") from None
        if not isinstance(record, dict):
            raise V.ToneForgeError(f"preset file {path.name} does not contain a JSON object")
        version = record.get("schema_version")
        if version is not None and int(version) > SCHEMA_VERSION:
            raise V.ToneForgeError(
                f"preset {path.name} was written by a newer ToneForge (schema {version}); "
                "update the plugin before reading it"
            )
        return record

    def _write_atomic(self, path: Path, record: dict[str, Any]) -> None:
        payload = json.dumps(record, indent=2, ensure_ascii=False, sort_keys=False)
        if len(payload.encode("utf-8")) > MAX_FILE_BYTES:
            raise V.ToneForgeError("preset is too large to store (over 1 MB)")
        handle = None
        temp_name = None
        try:
            fd, temp_name = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=str(path.parent))
            handle = os.fdopen(fd, "w", encoding="utf-8", newline="\n")
            handle.write(payload)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
            handle = None
            os.replace(temp_name, path)
            temp_name = None
        finally:
            if handle is not None:
                handle.close()
            if temp_name is not None and os.path.exists(temp_name):
                os.unlink(temp_name)
