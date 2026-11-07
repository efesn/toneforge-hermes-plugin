#!/usr/bin/env bash
# Install ToneForge into the active Hermes home and enable it.
#
#   ./scripts/install_hermes_plugin.sh              # copy + enable + verify
#   ./scripts/install_hermes_plugin.sh --no-enable  # copy only
#
# Safe to re-run: it replaces the installed copy but never touches
# <HERMES_HOME>/plugin-data/tone-forge (your presets and mappings).

set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
: "${HERMES_HOME:=${HOME}/.hermes}"
TARGET_DIR="${HERMES_HOME}/plugins/tone-forge"
ENABLE=1

for arg in "$@"; do
  case "$arg" in
    --no-enable) ENABLE=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [[ ! -f "${SOURCE_DIR}/plugin.yaml" ]]; then
  echo "error: ${SOURCE_DIR} does not look like the ToneForge plugin directory" >&2
  exit 1
fi
if ! command -v hermes >/dev/null 2>&1; then
  echo "error: the 'hermes' CLI is not on PATH" >&2
  exit 1
fi

echo "→ Hermes home : ${HERMES_HOME}"
echo "→ Source      : ${SOURCE_DIR}"
echo "→ Target      : ${TARGET_DIR}"

mkdir -p "${HERMES_HOME}/plugins"
rm -rf "${TARGET_DIR}"
cp -r "${SOURCE_DIR}" "${TARGET_DIR}"
find "${TARGET_DIR}" -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true

echo "→ Validating…"
hermes plugins validate "${TARGET_DIR}"
hermes plugins doctor "${TARGET_DIR}" --ci

if [[ "${ENABLE}" -eq 1 ]]; then
  echo "→ Enabling…"
  hermes plugins enable tone-forge
else
  echo "→ Skipped enabling (--no-enable). Run: hermes plugins enable tone-forge"
fi

echo
echo "Done. Restart the Hermes session so the toneforge_* tools are attached."
echo "Presets and mappings live in: ${HERMES_HOME}/plugin-data/tone-forge"
echo "Next: read docs/MIDI_SETUP_WINDOWS.md to wire up loopMIDI + AmpliTube."
