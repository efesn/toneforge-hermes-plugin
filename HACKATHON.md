# ToneForge — hackathon submission material

Draft copy for the Hermes Agent Plugin Hackathon. **Nothing here has been
submitted, published or posted** — it is ready for you to review and send.

---

## 1. GitHub repository description (short, ≤ 350 characters)

> ToneForge — an AI guitar tone engineer for AmpliTube 5 inside Hermes Agent.
> Describe a tone in plain language and get a complete, explained recipe (chain,
> amp/cab, mic, pedals, EQ, gate, levels), a versioned preset library, and a real
> MIDI bridge that moves the CCs you mapped — with no Python dependencies.

**Topics:** `hermes-agent` `hermes-plugin` `guitar` `tone` `amplitube` `midi`
`python` `music-production` `windows`

---

## 2. One-line pitch

> ToneForge turns "make it sound like Rammstein in Drop D" into a complete,
> explainable guitar-tone recipe — and then moves the AmpliTube knobs you mapped.

---

## 3. Submission summary (≈ 200 words)

ToneForge is a Hermes Agent plugin that acts as a guitar tone engineer for IK
Multimedia AmpliTube 5 Standalone on Windows. A single natural-language request —
genre, reference, tuning, pickup, purpose, gain, and free-text constraints in
English or Turkish — becomes a complete tone recipe: ordered signal chain, amp and
cabinet character with browser search terms, microphone placement, pedal settings,
7-band EQ, noise gate, normalised gain/bass/mid/treble/presence/master, and a
plain-language explanation of every decision, with explicit assumptions where the
request was silent.

A versioned JSON preset library stores, lists, adjusts and deletes recipes without
ever overwriting silently. The MIDI bridge needs **no third-party Python package**:
it drives the Windows `winmm` API through `ctypes`, falling back to `python-rtmidi`
when available — a deliberate answer to `python-rtmidi` having no wheel for new
CPython releases. CC mappings are user-owned, because AmpliTube has no default CC
assignments; the plugin stores what you learned in AmpliTube's own MIDI dialog,
converts 0-100 values into that mapping's CC range, and reports `applied:
"unverified"` rather than pretending the knob moved.

149 unit tests, no third-party Python dependencies, no network client of its own — plus a reference-track
analyser that measures a real recording (`ffmpeg`, and `yt-dlp` only when a URL is passed) instead of
guessing a style from a genre name. No native AmpliTube file format claims.

---

## 4. Feature list (as shipped)

**Design**
- 9 profiles (industrial, modern, thrash, metalcore, hard rock, classic rock, clean, ambient, lead)
- 10 tunings with real compensation (bass trim, high-pass, gate, presence)
- 6 pickup types with gain/treble/bass bias and noise-aware gating
- 6 purposes with gain caps and space policy
- 25 instruction modifiers + explicit numeric overrides, English and Turkish
- deterministic output, per-decision explanations, explicit assumptions

**Library**
- JSON presets with schema version, slug, version counter, timestamps, notes
- atomic writes, overwrite protection, confirm-gated deletion, path-traversal safety
- adjust without mutating; save in place (version bump) or save-as

**MIDI**
- `winmm` (stdlib `ctypes`) and optional `python-rtmidi` backends behind one interface
- explicit port selection, persisted; never an arbitrary port
- user-owned CC mappings with channel, CC range, parameter range, inversion, AmpliTube scope
- raw CC sending, mapped parameter setting with conversion report, MIDI-Learn probe
- honest result envelope: `applied: "unverified"`, `bytes_hex`, scope warnings

**Reference analysis (1.1)**

- `toneforge_analyze_reference`: local file or URL → octave and third-octave balance, spectral slope,
  95% rolloff, low-frequency tuning peaks, decay tail, stereo width
- `ffmpeg` decode + pure-Python radix-2 FFT: still no third-party Python packages
- measured numbers override the profile's params/EQ/gate/space, with provenance kept per value
- honest scope: the **mix** is measured, the amp model is inferred; a clip fade is never called reverb

**Engineering**
- 17 tools, strict schemas, JSON-string handlers that never raise
- 162 tests incl. reference analysis on synthetic `ffmpeg` fixtures and the URL guard
- `hermes plugins validate` → 15/15 checks; `hermes plugins doctor --ci` → 17 tools registered
- live MIDI egress verified on real Windows hardware

---

## 5. What is verified, and how

| Claim | Evidence |
|---|---|
| Tests pass | `python -m unittest discover -s tests` → `Ran 162 tests … OK` |
| Plugin validates | `hermes plugins validate ./tone-forge` → `Validation passed` (15 checks incl. declared-tools and security scan) |
| Plugin loads and registers | `hermes plugins doctor ./tone-forge --ci` → `17 tool(s), 0 hook(s)` |
| Real MIDI leaves the machine | `scripts/live_midi_check.py` → `B0 14 66` on `winmm`, rc 0, `LIVE MIDI SEND: OK` |
| No port is ever assumed | test + live: `send_midi` with no selection → error "never sends to a port you did not choose" |
| AmpliTube's MIDI rules are documented, not guessed | AmpliTube 5 manual ch. 5 (official PDF shipped with the app): CC/PC only, Global vs Preset scope, Min/Max percentages, Curve, receive channel |

## 6. What is *not* verified (stated up front)

- **AmpliTube receiving a message** — AmpliTube 5 is installed on the build machine,
  but no loopback MIDI port is, so the last hop is documented rather than
  demonstrated. The demo script cuts to AmpliTube only when a real port exists.
- **Model availability per edition** — hence "families + search terms", never model names.
- **Native `.at5p` presets** — deliberately unsupported. The format is not opaque: it is XML with model
  GUIDs resolvable from `AmpliTube 5.pak`. Writing one is a clone-and-rewrite job kept out of the plugin
  until it can be verified inside AmpliTube rather than merely parsed.

---

## 7. Judging-criteria notes

| Criterion | Where to look |
|---|---|
| Usefulness | the industrial-metal Drop D recipe is a genuinely good starting point, not filler |
| Depth of integration | hooks into real AmpliTube MIDI control, with its real constraints respected |
| Engineering quality | 162 tests, typed exceptions, atomic writes, no core imports, modular by concern |
| Honesty | explicit `applied: "unverified"`, measured-vs-inferred stated in every analysis response,
no invented model names, no `.at5p` fabrication |
| Documentation | README + feasibility report + Windows install + MIDI setup + architecture + 20 example prompts |

---

## 8. Suggested 3-bullet post / README banner

- 🎸 **ToneForge** — describe a tone, get the whole recipe, explained.
- 🎛 **Real MIDI bridge** — no `pip install`, talks to Windows' MIDI driver directly; moves only the CCs you assigned.
- 🧪 **162 tests, 17 tools, no third-party dependencies** — and it tells you what it cannot verify.
- 🎧 **Reference-track analysis** — give it a song; it measures the mix (bands, slope, rolloff, tuning,
  decay) and sets the recipe from the evidence, caveats attached.

---

## 9. Pre-submission checklist

Done:
- [x] Plugin built, validated, loaded by Hermes (17 tools, 162 tests)
- [x] `CHANGELOG.md` 1.1.0 matches `plugin.yaml` and `pyproject.toml`
- [x] README rewritten for 1.1.0 (counts, reference analysis, corrected `.at5p` claim, ffmpeg/yt-dlp rows)
- [x] `ARCHITECTURE.md`, `SECURITY.md`, `EXAMPLE_PROMPTS.md`, `INSTALLATION_WINDOWS.md`, `DEMO_SCRIPT.md` updated

Still to do (yours):
- [ ] **Push `main`** — commit `3207e75` is local only; the catalog PR must pin a pushed SHA
- [ ] Set the GitHub repo description + the nine topics from §1
- [ ] Replace `Copyright (c) 2026 ToneForge contributors` in `LICENSE` if you want your name
- [ ] Add at least one real screenshot to `docs/assets/` and reference it in the README gallery
- [ ] Record the demo: **under 90 seconds**, showing the plugin working (not slides)
- [ ] Post it on X tagging `@NousResearch`
- [ ] Open the catalog PR (§10), then submit the form with both links

---

## 10. Official entry steps

Deadline **Nov 11, 2026, 5:00 PM EST** = **Nov 12, 01:00 Türkiye saati**. Judged on usefulness, reliability,
polish and creativity.

1. **Catalog PR** — add exactly one file, `plugin-catalog/tone-forge.yaml`, to `NousResearch/hermes-agent`
   (fork → branch → PR). Full 40-char SHA, quoted version. Ready copy:
   [`hackathon/catalog-entry.yaml`](hackathon/catalog-entry.yaml).
2. **Demo video on X** — under 90 seconds, showing it working, tagging `@NousResearch`.
3. **Form** — both links: <https://form.typeform.com/to/FwJLvOln>

You can submit the form as soon as the PR is open; catalog CI runs when a maintainer starts it.
