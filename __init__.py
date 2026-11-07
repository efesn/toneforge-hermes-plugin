"""ToneForge - AI guitar tone engineer for IK Multimedia AmpliTube 5 (Standalone).

Hermes plugin entry point. ``register(ctx)`` is called once at startup; it wires
the tool schemas to their handlers and applies the plugin's settings.

Nothing here reaches the network, spawns a process or writes outside the
plugin's own data directory. MIDI output only happens when a tool is called with
an explicit port (or an explicitly selected one).
"""

from __future__ import annotations

import logging

from . import schemas, tools

logger = logging.getLogger(__name__)

__all__ = ["register"]

_DEFAULT_BACKEND = "auto"
_DEFAULT_CHANNEL = 1


def register(ctx) -> None:
    """Register every ToneForge tool with the host."""
    backend = _DEFAULT_BACKEND
    channel = _DEFAULT_CHANNEL
    try:
        backend = str(ctx.get_config("midi_backend", default=_DEFAULT_BACKEND) or _DEFAULT_BACKEND)
        channel = int(ctx.get_config("default_channel", default=_DEFAULT_CHANNEL) or _DEFAULT_CHANNEL)
    except Exception:  # pragma: no cover - config is best-effort
        logger.debug("ToneForge could not read plugin settings; using defaults", exc_info=True)

    if not 1 <= channel <= 16:
        logger.warning("ToneForge: default_channel %s is out of range; using 1", channel)
        channel = 1
    tools.configure(midi_backend=backend, default_channel=channel)

    registered = 0
    for schema in schemas.TOOLS:
        name = schema["name"]
        handler = tools.HANDLERS.get(name)
        if handler is None:  # pragma: no cover - guards a wiring mistake
            logger.error("ToneForge: no handler for %s", name)
            continue
        ctx.register_tool(
            name=name,
            toolset="toneforge",
            schema=schema,
            handler=handler,
            description=schema["description"].split(". ")[0],
            emoji="\U0001F3B8",
        )
        registered += 1
    logger.info("ToneForge registered %d tools (midi backend=%s, channel=%d)", registered, backend, channel)
