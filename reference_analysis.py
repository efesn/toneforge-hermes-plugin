"""Reference-audio analysis: turn a recording into tone-target overrides.

Why this exists: ``tone_engine`` designs from a *genre profile*, which is a prior, not
evidence. When the user names a song, the honest way to get closer is to measure the
recording - where its energy actually sits - and shape the guitar to fill that slot.

What this module is careful about:

* It analyses a **mix**, not an isolated guitar stem. Band balance, brightness and
  tail length are measurable; the amp model is not. Every result carries caveats.
* It uses ``ffmpeg`` for decoding and a small pure-Python FFT for spectra, so the
  plugin keeps its no-third-party-dependency property. No numpy.
* Nothing is downloaded unless the caller passes an explicit ``url``.

The output of :func:`derive_overrides` is a plain dict of ``params`` / ``eq`` /
``gate`` / ``space`` that :func:`tone_engine.apply_overrides` writes into a normal
tone configuration, so reference-driven presets stay byte-compatible with the rest
of the library.
"""

from __future__ import annotations

import array
import cmath
import math
import os
import shutil
import subprocess
import tempfile
from typing import Any, Optional

ANALYSIS_SR = 16000
NFFT = 4096
MAX_FRAMES = 32
EMPTY_BANDS = {63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800,
               1000, 1250, 1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000}

_GUITAR_LOW_STRINGS = {
    "standard E (E2 82.4)": 82.41,
    "Eb standard (Eb2 77.8)": 77.78,
    "D standard (D2 73.4)": 73.42,
    "drop D (D2 73.4)": 73.42,
    "drop C# (C#2 69.3)": 69.30,
    "drop C (C2 65.4)": 65.41,
    "B standard / 7-string (B1 61.7)": 61.74,
}


class AnalysisError(RuntimeError):
    """Raised when the audio cannot be decoded or the input is unusable."""


# --------------------------------------------------------------------------- #
# Tool discovery and decoding
# --------------------------------------------------------------------------- #

def ffmpeg() -> Optional[str]:
    return os.environ.get("TONEFORGE_FFMPEG") or shutil.which("ffmpeg")


def ffprobe() -> Optional[str]:
    return os.environ.get("TONEFORGE_FFPROBE") or shutil.which("ffprobe")


def yt_dlp() -> Optional[str]:
    return os.environ.get("TONEFORGE_YTDLP") or shutil.which("yt-dlp")


def probe_duration(path: str) -> Optional[float]:
    exe = ffprobe()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60, check=True,
        ).stdout.strip()
        return float(out)
    except Exception:
        return None


def download(url: str, workdir: str) -> tuple[str, dict[str, Any]]:
    """Fetch the audio track for a URL with yt-dlp. Returns (path, metadata)."""
    exe = yt_dlp()
    if not exe:
        raise AnalysisError(
            "yt-dlp is not installed, so this URL cannot be fetched. Install yt-dlp, or "
            "pass a local audio file path instead."
        )
    target = os.path.join(workdir, "reference.%(ext)s")
    cmd = [exe, "--no-playlist", "-f", "bestaudio/best", "-x", "--audio-format", "wav",
           "-o", target, url]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    produced = None
    for name in os.listdir(workdir):
        if name.startswith("reference.") and name.endswith(".wav"):
            produced = os.path.join(workdir, name)
            break
    if not produced:
        raise AnalysisError("yt-dlp did not produce an audio file: " + (proc.stderr or proc.stdout)[-400:])
    title = None
    for line in (proc.stdout or "").splitlines():
        if "[youtube]" in line and ":" in line and "Destination" not in line:
            continue
    try:
        meta = subprocess.run(
            [exe, "--no-playlist", "-J", url], capture_output=True, text=True, timeout=180
        )
        if meta.stdout:
            import json
            doc = json.loads(meta.stdout)
            title = doc.get("title")
            meta_out = {"title": title, "uploader": doc.get("uploader"), "duration_s": doc.get("duration")}
        else:
            meta_out = {"title": None}
    except Exception:
        meta_out = {"title": None}
    return produced, meta_out


def _decode(path: str, *, start: Optional[float], end: Optional[float],
            sr: int = ANALYSIS_SR, stereo: bool = False) -> tuple[list[float], list[float] | None]:
    exe = ffmpeg()
    if not exe:
        raise AnalysisError("ffmpeg was not found on PATH; set TONEFORGE_FFMPEG to its full path.")
    cmd = [exe, "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    if start is not None and end is not None and end > start:
        cmd += ["-t", f"{end - start:.3f}"]
    cmd += ["-i", path, "-vn", "-f", "s16le", "-acodec", "pcm_s16le",
            "-ar", str(sr), "-ac", "2" if stereo else "1", "pipe:1"]
    proc = subprocess.run(cmd, capture_output=True, timeout=300)
    if proc.returncode != 0 or not proc.stdout:
        raise AnalysisError("ffmpeg could not decode the audio: " + (proc.stderr.decode("utf-8", "replace")[-400:]))
    pcm = array.array("h")
    pcm.frombytes(proc.stdout[: len(proc.stdout) - (len(proc.stdout) % 2)])
    if stereo:
        left = [pcm[i] / 32768.0 for i in range(0, len(pcm), 2)]
        right = [pcm[i + 1] / 32768.0 for i in range(0, len(pcm), 2)]
        mid = [(a + b) / 2 for a, b in zip(left, right)]
        side = [(a - b) / 2 for a, b in zip(left, right)]
        return mid, side
    return [v / 32768.0 for v in pcm], None


# --------------------------------------------------------------------------- #
# Pure-Python FFT and spectral helpers
# --------------------------------------------------------------------------- #

def _fft(x: list[complex]) -> list[complex]:
    """Iterative radix-2 FFT. len(x) must be a power of two."""
    n = len(x)
    if n & (n - 1):
        raise ValueError("FFT length must be a power of two")
    j = 0
    for i in range(1, n):
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            x[i], x[j] = x[j], x[i]
    length = 2
    while length <= n:
        ang = -2 * math.pi / length
        wlen = [cmath.exp(1j * ang * k) for k in range(length // 2)]
        for i in range(0, n, length):
            for k in range(length // 2):
                u = x[i + k]
                v = x[i + k + length // 2] * wlen[k]
                x[i + k] = u + v
                x[i + k + length // 2] = u - v
        length <<= 1
    return x


def _hann(n: int) -> list[float]:
    return [0.5 - 0.5 * math.cos(2 * math.pi * i / (n - 1)) for i in range(n)]


def power_spectrum(samples: list[float], sr: int, nfft: int = NFFT) -> tuple[list[float], list[float]]:
    """Welch-style averaged power spectrum over at most MAX_FRAMES frames."""
    if len(samples) < nfft:
        raise AnalysisError(f"not enough audio for analysis ({len(samples)} samples at {sr} Hz)")
    window = _hann(nfft)
    hop = nfft // 2
    frames = min(MAX_FRAMES, max(1, (len(samples) - nfft) // hop + 1))
    if frames > 1:
        hop = max(hop, (len(samples) - nfft) // (frames - 1))
    psd = [0.0] * (nfft // 2 + 1)
    for f in range(frames):
        start = f * hop
        seg = samples[start:start + nfft]
        if len(seg) < nfft:
            break
        buf = [complex(seg[i] * window[i], 0.0) for i in range(nfft)]
        spec = _fft(buf)
        for k in range(nfft // 2 + 1):
            psd[k] += abs(spec[k]) ** 2
    total = float(frames)
    psd = [p / total for p in psd]
    freqs = [k * sr / nfft for k in range(nfft // 2 + 1)]
    return freqs, psd


def _band_db(freqs: list[float], psd: list[float], lo: float, hi: float) -> float:
    acc = 0.0
    n = 0
    for f, p in zip(freqs, psd):
        if lo <= f < hi:
            acc += p
            n += 1
    if not n:
        return -120.0
    return 10 * math.log10(acc / n + 1e-20)


def _octave_table(freqs: list[float], psd: list[float]) -> dict[str, float]:
    edges = [(20, 63), (63, 125), (125, 250), (250, 500), (500, 1000),
             (1000, 2000), (2000, 4000), (4000, 8000), (8000, 16000)]
    vals = {f"{lo}-{hi}": _band_db(freqs, psd, lo, hi) for lo, hi in edges}
    ref = max(vals.values())
    return {k: round(v - ref, 1) for k, v in vals.items()}


def _third_octave(freqs: list[float], psd: list[float]) -> dict[int, float]:
    out: dict[int, float] = {}
    for c in sorted(EMPTY_BANDS):
        lo, hi = c / 2 ** (1 / 6), c * 2 ** (1 / 6)
        out[c] = round(_band_db(freqs, psd, lo, hi), 1)
    ref = max(out.values())
    return {k: round(v - ref, 1) for k, v in out.items()}


def _shape(freqs: list[float], psd: list[float]) -> dict[str, float]:
    num = den = 0.0
    for f, p in zip(freqs, psd):
        if f >= 20:
            num += f * p
            den += p
    centroid = num / den if den else 0.0
    lx, ly = [], []
    for f, p in zip(freqs, psd):
        if 200 <= f <= 8000 and p > 0:
            lx.append(math.log2(f))
            ly.append(10 * math.log10(p))
    slope = 0.0
    if len(lx) > 2:
        mx = sum(lx) / len(lx)
        my = sum(ly) / len(ly)
        var = sum((v - mx) ** 2 for v in lx)
        if var:
            slope = sum((a - mx) * (b - my) for a, b in zip(lx, ly)) / var
    total = sum(p for f, p in zip(freqs, psd) if f >= 20)
    acc = 0.0
    rolloff = 0.0
    for f, p in zip(freqs, psd):
        if f < 20:
            continue
        acc += p
        if acc >= 0.95 * total:
            rolloff = f
            break
    mid = [(f, p) for f, p in zip(freqs, psd) if 300 <= f <= 4000]
    peak = max(mid, key=lambda t: t[1])[0] if mid else 0.0
    return {
        "centroid_hz": round(centroid, 1),
        "slope_db_per_oct": round(slope, 2),
        "rolloff95_hz": round(rolloff, 1),
        "mid_peak_hz": round(peak, 1),
    }


def _low_peaks(freqs: list[float], psd: list[float], lo: float = 40.0, hi: float = 200.0) -> list[dict[str, Any]]:
    idx = [(i, p) for i, (f, p) in enumerate(zip(freqs, psd)) if lo <= f <= hi]
    peaks: list[tuple[float, float]] = []
    for k in range(1, len(idx) - 1):
        i, p = idx[k]
        if p > idx[k - 1][1] and p > idx[k + 1][1]:
            peaks.append((freqs[i], 10 * math.log10(p + 1e-20)))
    peaks.sort(key=lambda t: -t[1])
    out = []
    for f, db in peaks[:6]:
        midi = 69 + 12 * math.log2(f / 440.0)
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        nearest = names[int(round(midi)) % 12]
        cents = 100 * (midi - round(midi))
        out.append({"hz": round(f, 2), "db": round(db, 1),
                    "nearest_note": nearest, "cents_off": round(cents, 1)})
    return out


def _tuning_guess(peaks: list[dict[str, Any]]) -> dict[str, Any]:
    if not peaks:
        return {"guess": None, "confidence": "none", "note": "no usable low-frequency peaks"}
    strongest = max(p["db"] for p in peaks)
    candidates = [p for p in peaks if p["db"] >= strongest - 12.0]
    best = None
    for label, hz in _GUITAR_LOW_STRINGS.items():
        if not candidates:
            continue
        cand = min(candidates, key=lambda p: abs(p["hz"] - hz))
        cents = 1200 * math.log2(cand["hz"] / hz)
        # 30 cents, not 60: the neighbouring semitone is ~100 cents away, and a bass-heavy
        # mix smears the low end enough that a loose threshold "matches" the wrong string.
        if abs(cents) <= 30 and (best is None or abs(cents) < abs(best[1])):
            best = (label, cents)
    if best is None:
        return {"guess": None, "confidence": "none",
                "note": "no low peak within 30 cents of any common low string - tuning not determined"}
    return {"guess": best[0], "cents_off": round(best[1], 1),
            "confidence": "low (full mix, bass and kick overlap the guitar's low string)"}


def _envelope(samples: list[float], sr: int, hop_s: float = 0.05) -> list[float]:
    hop = max(1, int(sr * hop_s))
    out = []
    for i in range(0, len(samples) - hop, hop):
        acc = 0.0
        for v in samples[i:i + hop]:
            acc += v * v
        out.append(10 * math.log10(acc / hop + 1e-20))
    return out


def _tail(samples: list[float], sr: int) -> dict[str, Any]:
    """Largest 30 dB decay found in the window, in seconds (a rough reverb/room hint)."""
    env = _envelope(samples, sr)
    if len(env) < 20:
        return {"t30_s": None}
    best = None
    for i in range(len(env) - 4):
        target = env[i] - 30
        for j in range(i + 1, len(env)):
            if env[j] <= target:
                if best is None or (j - i) > best:
                    best = j - i
                break
    if best is None:
        return {"t30_s": None}
    return {"t30_s": round(best * 0.05, 2)}


# --------------------------------------------------------------------------- #
# Public analysis
# --------------------------------------------------------------------------- #

CAVEATS = [
    "This analyses the full mix, not an isolated guitar stem: band balance and brightness are "
    "measurable, the amp model and pedal choices are inferred.",
    "Bass guitar and kick occupy the same 60-250 Hz region as the guitar's low strings, so the "
    "low-end read is a ceiling, not a measurement of the guitar.",
    "A mix that was mastered and streamed (lossy) will read slightly darker than the raw tracks.",
]


def analyze(path: str, *, start: Optional[float] = None, end: Optional[float] = None) -> dict[str, Any]:
    """Measure a recording (or a window of it) and return the metrics that drive the tone."""
    if not os.path.isfile(path):
        raise AnalysisError(f"no such audio file: {path}")
    duration = probe_duration(path)
    if end is None and duration is not None:
        end = min(duration, (start or 0.0) + 20.0)
    elif end is None:
        end = (start or 0.0) + 20.0
    mid, side = _decode(path, start=start, end=end, stereo=True)
    if not mid:
        raise AnalysisError("decoded no samples")
    freqs, psd = power_spectrum(mid, ANALYSIS_SR)
    # Low-string peaks need far better resolution than the tone-shaping spectrum: at 16 kHz a
    # 4096-point FFT has 3.9 Hz bins, which is ~90 cents at 74 Hz - useless for tuning.
    low_freqs, low_psd = freqs, psd
    try:
        low_freqs, low_psd = power_spectrum(mid, ANALYSIS_SR, nfft=16384)
    except AnalysisError:  # pragma: no cover - only for sub-second files
        pass
    result: dict[str, Any] = {
        "file": os.path.basename(path),
        "duration_s": round(duration, 2) if duration else None,
        "window_s": {"start": start, "end": end},
        "octave_bands_db": _octave_table(freqs, psd),
        "third_octave_db": _third_octave(freqs, psd),
        "shape": _shape(freqs, psd),
        "low_peaks": _low_peaks(low_freqs, low_psd),
        "low_peak_resolution_hz": round(low_freqs[1] - low_freqs[0], 2) if len(low_freqs) > 1 else None,
    }
    result["tuning"] = _tuning_guess(result["low_peaks"])
    window_len = (end - start) if (start is not None and end) else (end or 20.0)
    result["tail"] = _tail(mid, ANALYSIS_SR)
    if result["tail"].get("t30_s") and window_len and result["tail"]["t30_s"] > 0.5 * window_len:
        # A "decay" that outlasts half the window is the clip's own fade-out, not a reverb tail.
        result["tail"] = {
            "t30_s": None,
            "note": f"measured decay ({result['tail']['t30_s']} s) exceeds half the {window_len:.0f} s "
                    "window - treated as a clip fade, not a reverb measurement",
        }
    if not result["tail"].get("t30_s") and duration and duration > 25:
        # A continuous riff never decays 30 dB, so fall back to the end of the track,
        # where the last chord/cymbal tail is what the room actually does.
        try:
            tail_mid, _ = _decode(path, start=max(0.0, duration - 25.0), end=duration, stereo=False)
            tail = _tail(tail_mid, ANALYSIS_SR)
            if tail.get("t30_s"):
                tail["measured_on"] = "final 25 s of the track (the analysed window never decays)"
                result["tail"] = tail
        except AnalysisError:  # pragma: no cover - the window analysis already succeeded
            pass
    if side:
        _, psd_side = power_spectrum([a - b for a, b in zip(mid, side)], ANALYSIS_SR)
        width = {}
        for lo, hi in [(125, 250), (250, 500), (500, 1000), (1000, 2000), (2000, 4000)]:
            width[f"{lo}-{hi}"] = round(_band_db(freqs, psd_side, lo, hi) - _band_db(freqs, psd, lo, hi), 1)
        result["side_minus_mid_db"] = width
    result["caveats"] = list(CAVEATS)
    return result


def derive_overrides(metrics: dict[str, Any]) -> dict[str, Any]:
    """Turn measured mix balance into 0-100 tone parameters plus the reasons for them."""
    bands = metrics.get("octave_bands_db", {})
    thirds = metrics.get("third_octave_db", {})
    shape = metrics.get("shape", {})
    rolloff = float(shape.get("rolloff95_hz") or 6000.0)
    slope = float(shape.get("slope_db_per_oct") or -6.0)

    def band(key: str, default: float = -6.0) -> float:
        return float(bands.get(key, default))

    low_mid = band("125-250")
    voice = (band("500-1000") + band("1000-2000")) / 2
    upper = band("2000-4000")
    fizz = band("4000-8000")

    # --- EQ: mirror the record's guitar-slot contour, gently, and stay out of the bass
    def contour(hz: int, fallback: float) -> float:
        v = float(thirds.get(hz, fallback))
        base = (float(thirds.get(500, -6)) + float(thirds.get(1000, -6)) + float(thirds.get(2000, -6))) / 3

        def expected(f: float) -> float:
            return slope * math.log2(f / 1000.0)

        # Remove the mix's own spectral tilt: an EQ band should show the deviation from the
        # record's average slope, not that slope again (otherwise every high band is cut).
        expected_avg = (expected(500) + expected(1000) + expected(2000)) / 3
        residual = (v - base) - (expected(hz) - expected_avg)
        return round(max(-3.0, min(3.0, residual * 0.5)), 1)

    eq_bands = [
        {"hz": 100, "db": -3.0},
        {"hz": 200, "db": -2.0},
        {"hz": 400, "db": contour(400, -4.0)},
        {"hz": 800, "db": contour(800, -3.0)},
        {"hz": 1600, "db": contour(1600, -3.0)},
        {"hz": 3200, "db": contour(3150, -6.0)},
        {"hz": 6400, "db": round(max(-4.0, min(0.0, contour(6300, -14.0) - 1.0)), 1)},
    ]
    # The top is where a mastered modern mix is almost always darker than a raw amp
    high_cut = int(max(4500, min(12000, round(rolloff * 1.9 / 250) * 250)))
    low_cut = 100 if low_mid >= -1.0 else 90

    # --- amp voicing
    dark = slope < -6.0 or fizz < -8.0
    params = {
        "gain": 74 if dark else 70,
        "bass": 42 if low_mid < -1.0 else 38,
        "mid": 58 + (2 if voice > -4.0 else 0),
        "treble": 52 if dark else 56,
        "presence": 44 if dark else 49,
        "master": 55,
    }
    if upper - voice > 1.5:      # mix pushes 2-4 kHz: let the guitar share it, not own it
        params["presence"] = min(56, params["presence"] + 3)

    tail = float((metrics.get("tail") or {}).get("t30_s") or 0.0)
    reverb = 0.26 if tail >= 5.0 else 0.22
    delay = 0.16

    low_note = (metrics.get("tuning") or {}).get("guess")

    # --- amp/cab family hints, driven by the measured brightness and mid density
    guitar_region = (band("250-500") + band("500-1000") + band("1000-2000") + band("2000-4000")) / 4
    mid_forward = voice >= guitar_region - 1.0
    if dark and mid_forward:
        amp_hint = {
            "category": "High-gain channel with a mid-forward, raw bark",
            "family": "Hot-rodded British high gain (JCM800/plexi lineage) pushed by an overdrive",
            "character": "Raw and mid-heavy: it crunches and sags instead of staying stiff, and its top "
                         "end stops short of fizz",
            "search_terms": ["british", "jcm", "hot rodded", "high gain", "crunch", "lead channel"],
        }
    elif dark:
        amp_hint = {
            "category": "High-gain channel with a dense, dark voicing",
            "family": "Modern high gain with the treble backed off",
            "character": "Thick and compressed, with the top rolled away and the low mids carrying the weight",
            "search_terms": ["high gain", "modern", "rhythm channel", "dark"],
        }
    else:
        amp_hint = {
            "category": "High-gain channel with a bright, articulate top end",
            "family": "American modern high gain with a boost in front",
            "character": "Open and biting, with the pick attack clearly above the wash",
            "search_terms": ["high gain", "american", "modern", "rhythm channel"],
        }
    cabinet_hint = {
        "configuration": "Closed-back 4x12",
        "speaker_character": "Vintage-30 / Greenback family: strong 700 Hz-1.5 kHz midrange, soft top",
        "note": "A mid-forward cab is doing the voicing here; a scooped modern cab would erase the "
                "midrange the recording actually shows.",
    }

    why = [
        f"The record's energy peaks at {max(bands, key=bands.get) if bands else '125-250'} Hz and the "
        f"95% rolloff sits at {rolloff:.0f} Hz: the guitar has to stay out of the low mids and stop "
        f"well before the top, so low cut {low_cut} Hz / high cut {high_cut} Hz.",
        f"Slope is {slope:.1f} dB/octave with 4-8 kHz at {fizz:.1f} dB relative: "
        + ("a dark, blurred distortion - gain up, treble and presence down."
           if dark else "a brighter distortion - keep treble and presence up."),
        f"500 Hz-2 kHz sits at {voice:.1f} dB and 2-4 kHz at {upper:.1f} dB, so the midrange is "
        "carried flat rather than scooped; the EQ mirrors that contour instead of adding a fixed boost.",
        f"Measured tail of about {tail:.1f} s supports a long reverb at {reverb:.0%} mix"
        if tail else "No usable decay was found in the window, so the space setting stays conservative.",
    ]
    if low_note:
        why.append(f"The lowest strong partial matches {low_note}, which is why that tuning is suggested.")

    return {
        "params": params,
        "eq": {"low_cut_hz": low_cut, "high_cut_hz": high_cut, "bands": eq_bands},
        "gate": {"enabled": True, "threshold_db": -50.0, "decay_ms": 350, "hold_ms": 40},
        "space": {"delay_mix": delay, "reverb_mix": reverb},
        "amp": amp_hint,
        "cabinet": cabinet_hint,
        "tuning_hint": low_note,
        "why": why,
    }


def analyze_and_derive(path: str, *, start: Optional[float] = None,
                       end: Optional[float] = None) -> dict[str, Any]:
    metrics = analyze(path, start=start, end=end)
    return {"analysis": metrics, "overrides": derive_overrides(metrics)}


def temp_workspace() -> str:
    return tempfile.mkdtemp(prefix="toneforge-ref-")
