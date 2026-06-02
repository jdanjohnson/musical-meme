"""Core audio analysis — BPM, key, energy detection using librosa."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".flac", ".aiff", ".aif", ".m4a", ".ogg", ".wma", ".opus"}

# Camelot wheel mapping from musical key to Camelot code
# Key detection returns (pitch_class, mode) where mode: 0=minor, 1=major
# pitch_class: 0=C, 1=C#, 2=D, ..., 11=B
CAMELOT_MAP = {
    # Minor keys (A)
    (0, 0): "5A",    # C minor
    (1, 0): "12A",   # C#/Db minor
    (2, 0): "7A",    # D minor
    (3, 0): "2A",    # Eb minor
    (4, 0): "9A",    # E minor
    (5, 0): "4A",    # F minor
    (6, 0): "11A",   # F#/Gb minor
    (7, 0): "6A",    # G minor
    (8, 0): "1A",    # Ab minor
    (9, 0): "8A",    # A minor
    (10, 0): "3A",   # Bb minor
    (11, 0): "10A",  # B minor
    # Major keys (B)
    (0, 1): "8B",    # C major
    (1, 1): "3B",    # Db major
    (2, 1): "10B",   # D major
    (3, 1): "5B",    # Eb major
    (4, 1): "12B",   # E major
    (5, 1): "7B",    # F major
    (6, 1): "2B",    # F#/Gb major
    (7, 1): "9B",    # G major
    (8, 1): "4B",    # Ab major
    (9, 1): "11B",   # A major
    (10, 1): "6B",   # Bb major
    (11, 1): "1B",   # B major
}

KEY_NAMES = {
    (0, 0): "C minor", (1, 0): "C# minor", (2, 0): "D minor",
    (3, 0): "Eb minor", (4, 0): "E minor", (5, 0): "F minor",
    (6, 0): "F# minor", (7, 0): "G minor", (8, 0): "Ab minor",
    (9, 0): "A minor", (10, 0): "Bb minor", (11, 0): "B minor",
    (0, 1): "C major", (1, 1): "Db major", (2, 1): "D major",
    (3, 1): "Eb major", (4, 1): "E major", (5, 1): "F major",
    (6, 1): "F# major", (7, 1): "G major", (8, 1): "Ab major",
    (9, 1): "A major", (10, 1): "Bb major", (11, 1): "B major",
}

# Krumhansl-Kessler key profiles for key detection
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


@dataclass
class AnalysisResult:
    file_path: str
    file_hash: str
    file_size: int
    filename: str
    folder: str
    genre: str | None
    duration: float
    bpm: float
    bpm_confidence: float
    key: str
    key_confidence: float
    camelot: str
    energy: float
    loudness: float
    spectral_centroid: float
    energy_level: int
    brightness: float
    has_vocals: bool
    vocal_confidence: float
    intro_end_sec: float
    outro_start_sec: float
    phrase_length_sec: float
    format: str
    sample_rate: int
    channels: int
    analyzed_at: str
    file_modified_at: str
    # AI intelligence fields
    ai_genre: str | None = None
    ai_genre_confidence: float = 0.0
    mood_primary: str | None = None
    mood_valence: float = 0.0
    mood_arousal: float = 0.0
    mood_tension: float = 0.0
    mood_warmth: float = 0.0
    mood_tags: str | None = None  # JSON
    audio_embedding: str | None = None  # JSON
    structure_drops: str | None = None  # JSON
    structure_breakdowns: str | None = None  # JSON
    structure_builds: str | None = None  # JSON

    def to_dict(self) -> dict:
        return self.__dict__


def file_hash(filepath: str) -> str:
    """Quick hash using file size + first/last 8KB for speed on large files."""
    stat = os.stat(filepath)
    hasher = hashlib.md5()
    hasher.update(str(stat.st_size).encode())
    with open(filepath, "rb") as f:
        hasher.update(f.read(8192))
        if stat.st_size > 8192:
            f.seek(-8192, 2)
            hasher.update(f.read(8192))
    return hasher.hexdigest()


def detect_key(y: np.ndarray, sr: int) -> tuple[str, str, float]:
    """Detect musical key using chromagram correlation with key profiles.

    Returns (key_name, camelot_code, confidence).
    """
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_avg = np.mean(chroma, axis=1)

    # Normalize
    chroma_avg = chroma_avg / (np.linalg.norm(chroma_avg) + 1e-8)

    best_corr = -1.0
    best_key = (0, 1)

    for pitch_class in range(12):
        # Rotate profiles to test each key
        major_rotated = np.roll(MAJOR_PROFILE, pitch_class)
        minor_rotated = np.roll(MINOR_PROFILE, pitch_class)

        major_rotated = major_rotated / (np.linalg.norm(major_rotated) + 1e-8)
        minor_rotated = minor_rotated / (np.linalg.norm(minor_rotated) + 1e-8)

        corr_major = np.corrcoef(chroma_avg, major_rotated)[0, 1]
        corr_minor = np.corrcoef(chroma_avg, minor_rotated)[0, 1]

        if corr_major > best_corr:
            best_corr = corr_major
            best_key = (pitch_class, 1)
        if corr_minor > best_corr:
            best_corr = corr_minor
            best_key = (pitch_class, 0)

    key_name = KEY_NAMES[best_key]
    camelot = CAMELOT_MAP[best_key]
    confidence = max(0.0, min(1.0, best_corr))

    return key_name, camelot, confidence


def detect_bpm(y: np.ndarray, sr: int) -> tuple[float, float]:
    """Detect BPM using multiple methods and picking the best estimate.

    Uses librosa's beat tracker, onset-based tempogram, and autocorrelation
    to avoid snapping all tracks to the same BPM.

    Returns (bpm, confidence).
    """
    estimates: list[tuple[float, float]] = []  # (bpm, weight)

    # Method 1: beat_track (default)
    try:
        tempo1, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        bpm1 = float(np.atleast_1d(tempo1)[0])
        # Confidence from beat regularity
        if len(beat_frames) >= 4:
            bt = librosa.frames_to_time(beat_frames, sr=sr)
            intervals = np.diff(bt)
            cv = float(np.std(intervals) / (np.mean(intervals) + 1e-8))
            conf1 = max(0.0, min(1.0, 1.0 - cv))
        else:
            conf1 = 0.3
        estimates.append((bpm1, conf1))
    except Exception:
        pass

    # Method 2: onset-based tempo estimation
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempo2 = librosa.feature.tempo(onset_envelope=onset_env, sr=sr)
        bpm2 = float(np.atleast_1d(tempo2)[0])
        estimates.append((bpm2, 0.7))
    except Exception:
        pass

    # Method 3: tempogram autocorrelation (different algorithm, better for
    # tracks where beat_track snaps to a grid)
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
        # Find the dominant tempo from the tempogram
        avg_tempogram = np.mean(tempogram, axis=1)
        # Convert bin index to BPM
        bpm_bins = librosa.tempo_frequencies(tempogram.shape[0], sr=sr)
        # Only consider 60-200 BPM range
        valid = (bpm_bins >= 60) & (bpm_bins <= 200)
        if np.any(valid):
            masked = avg_tempogram.copy()
            masked[~valid] = 0
            best_idx = int(np.argmax(masked))
            bpm3 = float(bpm_bins[best_idx])
            if 60 <= bpm3 <= 200:
                estimates.append((bpm3, 0.5))
    except Exception:
        pass

    if not estimates:
        return 120.0, 0.1

    # If all estimates agree within 2 BPM, use weighted average
    bpms = [e[0] for e in estimates]
    weights = [e[1] for e in estimates]

    if max(bpms) - min(bpms) < 2.0:
        # Very close — weighted average
        avg = sum(b * w for b, w in zip(bpms, weights)) / sum(weights)
        conf = max(weights)
        return round(avg, 2), round(conf, 3)

    # Estimates disagree — use the one with highest confidence
    # but add small random offset to break grid-snapping
    best_idx = int(np.argmax(weights))
    best_bpm = estimates[best_idx][0]
    best_conf = estimates[best_idx][1]

    # Check for half/double time confusion
    for bpm_est, w in estimates:
        if abs(bpm_est - best_bpm * 2) < 4:
            # Candidate might be double time — prefer the lower if in dance range
            if 100 <= best_bpm <= 160:
                pass  # keep the lower one
            elif 100 <= bpm_est / 2 <= 160:
                best_bpm = bpm_est / 2
        elif abs(bpm_est - best_bpm / 2) < 4:
            if 100 <= bpm_est <= 160:
                best_bpm = bpm_est

    return round(best_bpm, 2), round(best_conf, 3)


def compute_energy(y: np.ndarray, sr: int) -> tuple[float, float, float, float, int]:
    """Compute energy metrics.

    Returns (energy_rms, loudness_db, spectral_centroid_hz, brightness, energy_level_1_10).
    """
    # RMS energy
    rms = librosa.feature.rms(y=y)[0]
    energy_rms = float(np.mean(rms))

    # Loudness in dB
    loudness = float(librosa.amplitude_to_db(np.array([energy_rms]), ref=1.0)[0])

    # Spectral centroid (brightness indicator)
    cent = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
    spectral_centroid = float(np.mean(cent))

    # Normalize brightness to 0-1 (typical centroid range 500-8000 Hz)
    brightness = min(1.0, max(0.0, (spectral_centroid - 500) / 7500))

    # Energy level 1-10 combining RMS, brightness, and spectral features
    # Normalize RMS (typical range 0.01 - 0.3)
    rms_norm = min(1.0, max(0.0, (energy_rms - 0.01) / 0.29))
    energy_score = 0.6 * rms_norm + 0.4 * brightness
    energy_level = max(1, min(10, round(energy_score * 9 + 1)))

    return (
        round(energy_rms, 4),
        round(loudness, 2),
        round(spectral_centroid, 2),
        round(brightness, 3),
        energy_level,
    )


def detect_vocals(y: np.ndarray, sr: int) -> tuple[bool, float]:
    """Detect vocal presence using spectral contrast and MFCCs.

    Vocals have distinctive spectral characteristics:
    - High spectral contrast in the 300-3000 Hz range (voice fundamental + harmonics)
    - Specific MFCC patterns (MFCCs 1-4 carry vocal formant info)
    - Higher spectral flatness in vocal regions vs. purely instrumental

    Returns (has_vocals: bool, confidence: 0.0-1.0).
    """
    # Spectral contrast — vocals increase contrast in mid-frequency bands
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr, n_bands=6)
    mid_contrast = float(np.mean(contrast[2:5]))  # bands covering ~300-3000 Hz

    # MFCCs — vocal tracks have higher variance in MFCCs 1-4
    mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_var = float(np.mean(np.var(mfccs[1:5], axis=1)))

    # Spectral flatness — vocals are more tonal (lower flatness) than noise
    flatness = librosa.feature.spectral_flatness(y=y)
    avg_flatness = float(np.mean(flatness))

    # Zero crossing rate — speech/vocals have moderate ZCR
    zcr = librosa.feature.zero_crossing_rate(y)
    avg_zcr = float(np.mean(zcr))

    # Scoring heuristic combining multiple indicators
    vocal_score = 0.0

    # Mid-band spectral contrast > 20 suggests vocals
    if mid_contrast > 25:
        vocal_score += 0.35
    elif mid_contrast > 18:
        vocal_score += 0.2

    # High MFCC variance indicates vocal formants
    if mfcc_var > 100:
        vocal_score += 0.35
    elif mfcc_var > 50:
        vocal_score += 0.2

    # Low-to-moderate flatness (tonal content like voice)
    if 0.01 < avg_flatness < 0.15:
        vocal_score += 0.15

    # Moderate ZCR typical of voice
    if 0.03 < avg_zcr < 0.12:
        vocal_score += 0.15

    confidence = min(1.0, vocal_score)
    has_vocals = confidence >= 0.5

    return has_vocals, confidence


def detect_transition_points(y: np.ndarray, sr: int, bpm: float) -> dict:
    """Detect intro/outro cue points for DJ transitions.

    Uses energy envelope with smoothing to find where the track's energy
    first rises (end of intro) and where it begins its final drop (start
    of outro). Points are snapped to phrase boundaries (every 16 beats).

    Returns {intro_end_sec, outro_start_sec, phrase_length_sec}.
    """
    if bpm <= 0:
        bpm = 120.0

    beat_dur = 60.0 / bpm
    phrase_beats = 16
    phrase_dur = beat_dur * phrase_beats

    duration = librosa.get_duration(y=y, sr=sr)

    # Compute energy envelope in ~0.25s windows for better resolution
    hop = max(1, int(sr * 0.25))
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    if len(rms) == 0:
        return {"intro_end_sec": 0, "outro_start_sec": duration, "phrase_length_sec": phrase_dur}

    # Smooth the envelope to reduce noise
    kernel_size = max(3, int(2.0 / 0.25))  # ~2 second smoothing
    if len(rms) > kernel_size:
        kernel = np.ones(kernel_size) / kernel_size
        rms_smooth = np.convolve(rms, kernel, mode="same")
    else:
        rms_smooth = rms

    rms_norm = rms_smooth / (np.max(rms_smooth) + 1e-8)
    times = librosa.frames_to_time(np.arange(len(rms_norm)), sr=sr, hop_length=hop)

    # --- Intro detection ---
    # Find where energy first stays above 30% for at least 2 seconds
    threshold_intro = 0.3
    min_sustain_frames = max(1, int(2.0 / 0.25))
    intro_end = 0.0
    consecutive = 0
    for i, val in enumerate(rms_norm):
        if val >= threshold_intro:
            consecutive += 1
            if consecutive >= min_sustain_frames:
                intro_end = times[max(0, i - min_sustain_frames + 1)]
                break
        else:
            consecutive = 0

    # Snap to phrase boundary
    if phrase_dur > 0:
        intro_end = max(phrase_dur, round(intro_end / phrase_dur) * phrase_dur)

    # --- Outro detection ---
    # Walk backwards from the end: find where energy drops below 25% of peak
    # sustained for at least 2 seconds. The outro starts where the drop begins.
    threshold_outro = 0.25
    outro_start = duration
    consecutive = 0
    for i in range(len(rms_norm) - 1, -1, -1):
        if rms_norm[i] < threshold_outro:
            consecutive += 1
            if consecutive >= min_sustain_frames:
                # The outro begins where the energy started dropping
                # Walk forward to find the last high-energy frame before this dip
                drop_start_idx = min(len(rms_norm) - 1, i + consecutive)
                outro_start = times[drop_start_idx]
                break
        else:
            consecutive = 0

    # If we didn't find a clear drop, look for where energy derivative goes negative
    if outro_start >= duration - phrase_dur:
        # Use the last 25% of the track and find the steepest energy decline
        last_quarter = max(1, int(len(rms_norm) * 0.75))
        if last_quarter < len(rms_norm) - 1:
            diff = np.diff(rms_norm[last_quarter:])
            if len(diff) > 0:
                steepest = np.argmin(diff)
                outro_start = times[last_quarter + steepest]

    # Snap to phrase boundary
    if phrase_dur > 0:
        outro_start = min(duration - phrase_dur, round(outro_start / phrase_dur) * phrase_dur)

    # Ensure outro is at least 2 phrases from the end and after intro
    outro_start = max(outro_start, intro_end + phrase_dur)
    outro_start = min(outro_start, duration - phrase_dur)

    # Sanity: outro should leave at least 8 seconds for crossfade
    if duration - outro_start < 8:
        outro_start = max(intro_end + phrase_dur, duration - max(16, phrase_dur * 2))

    return {
        "intro_end_sec": round(intro_end, 2),
        "outro_start_sec": round(outro_start, 2),
        "phrase_length_sec": round(phrase_dur, 2),
    }


def _clean_genre_name(raw: str) -> str:
    """Clean up a folder-derived genre name.

    Removes timestamps, date suffixes, 'Copy of' prefixes, and normalizes
    separators so folder names like 'Best House remixes of popular songs
    2-2025-12-26T03_05_30' become 'House Remixes'.
    """
    import re as _re

    name = raw.strip()
    if not name:
        return "Unknown"

    # Remove 'Copy of ' prefix
    name = _re.sub(r"^(?:Copy\s+of\s+)", "", name, flags=_re.IGNORECASE)

    # Remove trailing timestamps (ISO-like): -2025-12-26T03_05_30, _2025-12-26, etc.
    name = _re.sub(r"[\s_\-]*\d{4}[\-_]\d{2}[\-_]\d{2}(?:T\d{2}[\-_:]\d{2}[\-_:]\d{2})?$", "", name)

    # Remove trailing numbers / IDs like ' 2', '-3'
    name = _re.sub(r"[\s_\-]+\d{1,2}$", "", name)

    # Replace underscores with spaces
    name = name.replace("_", " ")

    # Remove filler words for cleaner genre labels
    name = _re.sub(r"\b(?:of|the|and|best|popular|songs)\b", "", name, flags=_re.IGNORECASE)

    # Collapse whitespace
    name = _re.sub(r"\s+", " ", name).strip()

    # Title case
    if name:
        name = name.title()

    return name if name else "Unknown"


def infer_genre_from_path(filepath: str, root_folder: str | None = None) -> str | None:
    """Infer genre from folder structure.

    If root_folder is given, use the first subfolder as genre.
    Otherwise use the parent folder name. Cleans up timestamps, prefixes,
    and other artifacts from folder names.
    """
    path = Path(filepath)
    raw = None
    if root_folder:
        root = Path(root_folder)
        try:
            relative = path.relative_to(root)
            parts = relative.parts
            if len(parts) > 1:
                raw = parts[0]
        except ValueError:
            pass
    if raw is None:
        raw = path.parent.name
    return _clean_genre_name(raw)


def scan_folder(folder: str) -> list[str]:
    """Recursively find all supported audio files in a folder."""
    files = []
    for root, _dirs, filenames in os.walk(folder):
        for fname in filenames:
            if Path(fname).suffix.lower() in SUPPORTED_EXTENSIONS:
                files.append(os.path.join(root, fname))
    files.sort()
    return files


def analyze_track(filepath: str, root_folder: str | None = None) -> AnalysisResult:
    """Analyze a single audio track. This is the heavy computation."""
    logger.info("Analyzing: %s", filepath)
    path = Path(filepath)
    stat = os.stat(filepath)

    # Load audio (mono, 22050 Hz for analysis — standard librosa)
    y, sr = librosa.load(filepath, sr=22050, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)

    # Get file info from soundfile if possible
    try:
        info = sf.info(filepath)
        sample_rate = info.samplerate
        channels = info.channels
    except Exception:
        sample_rate = sr
        channels = 1

    # BPM detection
    bpm, bpm_confidence = detect_bpm(y, sr)

    # Key detection
    key_name, camelot, key_confidence = detect_key(y, sr)

    # Energy analysis
    energy_rms, loudness, spectral_centroid, brightness, energy_level = compute_energy(y, sr)

    # Vocal detection
    has_vocals, vocal_confidence = detect_vocals(y, sr)

    # Transition points (intro/outro cue points)
    cue_points = detect_transition_points(y, sr, bpm)

    # Genre from folder (fallback)
    genre = infer_genre_from_path(filepath, root_folder)

    # AI Intelligence analysis
    from app.intelligence import analyze_intelligence
    try:
        intel = analyze_intelligence(
            y, sr, bpm, brightness, energy_level, has_vocals, key_name
        )
    except Exception as e:
        logger.warning("AI intelligence analysis failed for %s: %s", filepath, e)
        intel = {}

    return AnalysisResult(
        file_path=filepath,
        file_hash=file_hash(filepath),
        file_size=stat.st_size,
        filename=path.name,
        folder=str(path.parent),
        genre=genre,
        duration=round(duration, 2),
        bpm=bpm,
        bpm_confidence=bpm_confidence,
        key=key_name,
        key_confidence=key_confidence,
        camelot=camelot,
        energy=round(energy_rms, 4),
        loudness=loudness,
        spectral_centroid=spectral_centroid,
        energy_level=energy_level,
        brightness=brightness,
        has_vocals=has_vocals,
        vocal_confidence=round(vocal_confidence, 3),
        intro_end_sec=cue_points["intro_end_sec"],
        outro_start_sec=cue_points["outro_start_sec"],
        phrase_length_sec=cue_points["phrase_length_sec"],
        format=path.suffix.lstrip(".").upper(),
        sample_rate=sample_rate,
        channels=channels,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        # AI intelligence
        ai_genre=intel.get("ai_genre"),
        ai_genre_confidence=intel.get("ai_genre_confidence", 0.0),
        mood_primary=intel.get("mood", {}).get("primary"),
        mood_valence=intel.get("mood", {}).get("valence", 0.0),
        mood_arousal=intel.get("mood", {}).get("arousal", 0.0),
        mood_tension=intel.get("mood", {}).get("tension", 0.0),
        mood_warmth=intel.get("mood", {}).get("warmth", 0.0),
        mood_tags=json.dumps(intel.get("mood", {}).get("tags", [])),
        audio_embedding=json.dumps(intel.get("embedding", [])),
        structure_drops=json.dumps(intel.get("structure", {}).get("drops", [])),
        structure_breakdowns=json.dumps(intel.get("structure", {}).get("breakdowns", [])),
        structure_builds=json.dumps(intel.get("structure", {}).get("builds", [])),
    )
