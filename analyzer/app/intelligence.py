"""AI-powered audio intelligence — genre classification, mood detection,
audio embeddings, smart transition points, and transition compatibility scoring.

Uses librosa spectral features + scikit-learn for lightweight ML that runs
on any machine without GPU or heavy model downloads.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import librosa
import numpy as np
from sklearn.preprocessing import normalize as sk_normalize

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Audio Embedding — a compact vector that captures how a track *sounds*
# ---------------------------------------------------------------------------

def compute_audio_embedding(y: np.ndarray, sr: int) -> list[float]:
    """Compute a 128-dimensional embedding that captures timbral, rhythmic,
    and tonal characteristics of a track.

    The embedding is a concatenation of:
    - 20 MFCCs (mean + std = 40 dims) — timbral texture
    - 12 chroma (mean = 12 dims) — tonal content
    - 7 spectral features (centroid, bandwidth, contrast×6, rolloff, flatness,
      zcr, tonnetz mean = 26 dims) — frequency distribution
    - Tempogram summary (10 dims) — rhythmic pattern
    - Onset strength stats (4 dims) — percussive character
    - Mel spectrogram band energies (36 dims) — frequency balance

    Total: 128 dims, L2-normalized.
    """
    features = []

    # MFCCs — timbral fingerprint
    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        features.extend(np.mean(mfcc, axis=1).tolist())  # 20
        features.extend(np.std(mfcc, axis=1).tolist())    # 20
    except Exception:
        features.extend([0.0] * 40)

    # Chroma — tonal content
    try:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        features.extend(np.mean(chroma, axis=1).tolist())  # 12
    except Exception:
        features.extend([0.0] * 12)

    # Spectral features
    try:
        cent = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))
        bw = np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr))
        rolloff = np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr))
        flat = np.mean(librosa.feature.spectral_flatness(y=y))
        zcr = np.mean(librosa.feature.zero_crossing_rate(y))
        # Spectral contrast across 6 bands
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_mean = np.mean(contrast, axis=1)  # 7 bands
        features.extend([cent / 8000, bw / 8000, rolloff / sr])  # 3 normalized
        features.extend((contrast_mean / 50).tolist())            # 7
        features.extend([flat, zcr])                               # 2
    except Exception:
        features.extend([0.0] * 12)

    # Tonnetz — tonal centroid features (harmonic content)
    try:
        tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
        features.extend(np.mean(tonnetz, axis=1).tolist())  # 6
    except Exception:
        features.extend([0.0] * 6)

    # Tempogram — rhythmic pattern summary
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        tempogram = librosa.feature.tempogram(onset_envelope=onset_env, sr=sr)
        # Take mean across time for top 10 tempo bins
        tempo_profile = np.mean(tempogram, axis=1)
        top_indices = np.argsort(tempo_profile)[-10:]
        features.extend(tempo_profile[top_indices].tolist())  # 10
    except Exception:
        features.extend([0.0] * 10)

    # Onset strength stats — percussive character
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        features.extend([
            float(np.mean(onset_env)),
            float(np.std(onset_env)),
            float(np.max(onset_env)),
            float(np.median(onset_env)),
        ])  # 4
    except Exception:
        features.extend([0.0] * 4)

    # Mel spectrogram band energies — frequency balance across 36 bands
    try:
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=36)
        mel_db = librosa.power_to_db(mel, ref=np.max)
        features.extend(np.mean(mel_db, axis=1).tolist())  # 36
    except Exception:
        features.extend([0.0] * 36)

    # Pad or truncate to exactly 128
    features = features[:128]
    while len(features) < 128:
        features.append(0.0)

    # L2 normalize
    vec = np.array(features, dtype=np.float64).reshape(1, -1)
    vec = sk_normalize(vec, norm="l2")[0]
    return [round(float(v), 6) for v in vec]


def embedding_similarity(emb_a: list[float], emb_b: list[float]) -> float:
    """Cosine similarity between two embeddings (already L2-normalized)."""
    a = np.array(emb_a)
    b = np.array(emb_b)
    return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# 2. AI Genre Classification — from audio features, not folder names
# ---------------------------------------------------------------------------

# Genre signatures: typical spectral feature ranges for electronic subgenres.
# Each entry defines expected ranges for key features.
_GENRE_SIGNATURES: dict[str, dict] = {
    "tech-house": {
        "bpm": (122, 132), "brightness": (0.2, 0.45), "energy_level": (5, 8),
        "spectral_flatness": (0.01, 0.15), "has_vocals": None,
        "bass_heavy": True, "percussive": True,
    },
    "deep-house": {
        "bpm": (118, 128), "brightness": (0.1, 0.3), "energy_level": (3, 6),
        "spectral_flatness": (0.005, 0.1), "has_vocals": None,
        "bass_heavy": True, "percussive": False,
    },
    "melodic-techno": {
        "bpm": (120, 135), "brightness": (0.15, 0.35), "energy_level": (5, 8),
        "spectral_flatness": (0.02, 0.12), "has_vocals": False,
        "bass_heavy": False, "percussive": True,
    },
    "minimal-techno": {
        "bpm": (125, 138), "brightness": (0.15, 0.35), "energy_level": (4, 7),
        "spectral_flatness": (0.03, 0.2), "has_vocals": False,
        "bass_heavy": False, "percussive": True,
    },
    "progressive-house": {
        "bpm": (120, 132), "brightness": (0.2, 0.4), "energy_level": (5, 8),
        "spectral_flatness": (0.01, 0.1), "has_vocals": None,
        "bass_heavy": False, "percussive": False,
    },
    "house-remix": {
        "bpm": (122, 132), "brightness": (0.15, 0.4), "energy_level": (5, 9),
        "spectral_flatness": (0.01, 0.15), "has_vocals": True,
        "bass_heavy": True, "percussive": True,
    },
    "disco-house": {
        "bpm": (118, 128), "brightness": (0.25, 0.5), "energy_level": (5, 8),
        "spectral_flatness": (0.01, 0.1), "has_vocals": True,
        "bass_heavy": False, "percussive": False,
    },
    "afro-house": {
        "bpm": (118, 128), "brightness": (0.2, 0.4), "energy_level": (5, 7),
        "spectral_flatness": (0.01, 0.12), "has_vocals": None,
        "bass_heavy": True, "percussive": True,
    },
    "edm": {
        "bpm": (126, 132), "brightness": (0.3, 0.55), "energy_level": (7, 10),
        "spectral_flatness": (0.02, 0.2), "has_vocals": True,
        "bass_heavy": True, "percussive": True,
    },
    "downtempo": {
        "bpm": (80, 115), "brightness": (0.1, 0.3), "energy_level": (1, 4),
        "spectral_flatness": (0.005, 0.08), "has_vocals": None,
        "bass_heavy": False, "percussive": False,
    },
    "drum-and-bass": {
        "bpm": (160, 180), "brightness": (0.25, 0.5), "energy_level": (7, 10),
        "spectral_flatness": (0.03, 0.2), "has_vocals": None,
        "bass_heavy": True, "percussive": True,
    },
    "indie-dance": {
        "bpm": (110, 128), "brightness": (0.2, 0.45), "energy_level": (4, 7),
        "spectral_flatness": (0.01, 0.1), "has_vocals": True,
        "bass_heavy": False, "percussive": False,
    },
}


def classify_genre(
    y: np.ndarray,
    sr: int,
    bpm: float,
    brightness: float,
    energy_level: int,
    has_vocals: bool,
) -> tuple[str, float]:
    """Classify a track's genre from its audio features.

    Returns (genre_name, confidence 0-1).
    """
    # Compute extra features for classification
    try:
        flat = float(np.mean(librosa.feature.spectral_flatness(y=y)))
    except Exception:
        flat = 0.05

    # Bass heaviness: energy ratio in low frequencies (< 300 Hz)
    try:
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=64)
        mel_db = librosa.power_to_db(mel, ref=np.max)
        freq_bins = librosa.mel_frequencies(n_mels=64, fmax=sr / 2)
        bass_bins = freq_bins < 300
        mid_bins = (freq_bins >= 300) & (freq_bins < 2000)
        bass_energy = float(np.mean(mel_db[bass_bins]))
        mid_energy = float(np.mean(mel_db[mid_bins]))
        is_bass_heavy = bass_energy > mid_energy - 5
    except Exception:
        is_bass_heavy = False

    # Percussiveness: onset strength variance
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        percussiveness = float(np.std(onset_env) / (np.mean(onset_env) + 1e-8))
        is_percussive = percussiveness > 0.8
    except Exception:
        is_percussive = False

    # Score each genre
    scores: list[tuple[str, float]] = []

    for genre, sig in _GENRE_SIGNATURES.items():
        score = 0.0
        checks = 0

        # BPM fit
        bpm_lo, bpm_hi = sig["bpm"]
        checks += 1
        if bpm_lo <= bpm <= bpm_hi:
            score += 1.0
        elif abs(bpm - bpm_lo) < 5 or abs(bpm - bpm_hi) < 5:
            score += 0.5

        # Brightness fit
        br_lo, br_hi = sig["brightness"]
        checks += 1
        if br_lo <= brightness <= br_hi:
            score += 1.0
        elif abs(brightness - br_lo) < 0.05 or abs(brightness - br_hi) < 0.05:
            score += 0.4

        # Energy level fit
        e_lo, e_hi = sig["energy_level"]
        checks += 1
        if e_lo <= energy_level <= e_hi:
            score += 1.0
        elif abs(energy_level - e_lo) <= 1 or abs(energy_level - e_hi) <= 1:
            score += 0.5

        # Spectral flatness fit
        f_lo, f_hi = sig["spectral_flatness"]
        checks += 1
        if f_lo <= flat <= f_hi:
            score += 1.0
        elif flat < f_hi * 1.5:
            score += 0.3

        # Vocals
        if sig["has_vocals"] is not None:
            checks += 1
            if sig["has_vocals"] == has_vocals:
                score += 1.0
            else:
                score += 0.2

        # Bass heaviness
        if sig.get("bass_heavy") is not None:
            checks += 1
            if sig["bass_heavy"] == is_bass_heavy:
                score += 0.8
            else:
                score += 0.2

        # Percussiveness
        if sig.get("percussive") is not None:
            checks += 1
            if sig["percussive"] == is_percussive:
                score += 0.8
            else:
                score += 0.2

        confidence = score / max(1, checks)
        scores.append((genre, confidence))

    scores.sort(key=lambda x: x[1], reverse=True)

    if scores and scores[0][1] > 0.3:
        return scores[0][0], round(scores[0][1], 3)
    return "electronic", 0.2


# ---------------------------------------------------------------------------
# 3. Mood Detection — from spectral characteristics
# ---------------------------------------------------------------------------

@dataclass
class MoodProfile:
    """Multi-dimensional mood detected from audio."""
    primary: str           # dominant mood label
    confidence: float      # 0-1
    valence: float         # -1 (dark/sad) to +1 (bright/happy)
    arousal: float         # -1 (calm) to +1 (energetic)
    tension: float         # 0 (relaxed) to 1 (tense/aggressive)
    warmth: float          # 0 (cold/sterile) to 1 (warm/lush)
    tags: list[str]        # descriptive mood tags

    def to_dict(self) -> dict:
        return {
            "primary": self.primary,
            "confidence": self.confidence,
            "valence": self.valence,
            "arousal": self.arousal,
            "tension": self.tension,
            "warmth": self.warmth,
            "tags": self.tags,
        }


_MOOD_LABELS = {
    # (valence_range, arousal_range) -> label
    "euphoric":   {"valence": (0.3, 1.0),  "arousal": (0.3, 1.0),  "tension": (0.0, 0.4)},
    "energetic":  {"valence": (0.0, 0.5),  "arousal": (0.5, 1.0),  "tension": (0.0, 0.5)},
    "aggressive": {"valence": (-1.0, 0.0), "arousal": (0.5, 1.0),  "tension": (0.5, 1.0)},
    "dark":       {"valence": (-1.0, -0.2),"arousal": (0.0, 0.5),  "tension": (0.3, 1.0)},
    "melancholic":{"valence": (-0.8, 0.0), "arousal": (-1.0, 0.0), "tension": (0.0, 0.5)},
    "chill":      {"valence": (0.0, 0.6),  "arousal": (-1.0, -0.1),"tension": (0.0, 0.3)},
    "dreamy":     {"valence": (0.0, 0.5),  "arousal": (-0.5, 0.2), "tension": (0.0, 0.2)},
    "groovy":     {"valence": (0.1, 0.7),  "arousal": (0.1, 0.6),  "tension": (0.0, 0.3)},
    "hypnotic":   {"valence": (-0.3, 0.3), "arousal": (0.0, 0.5),  "tension": (0.1, 0.5)},
    "uplifting":  {"valence": (0.4, 1.0),  "arousal": (0.2, 0.8),  "tension": (0.0, 0.3)},
}


def detect_mood(y: np.ndarray, sr: int, key: str = "", energy_level: int = 5) -> MoodProfile:
    """Detect mood from audio using spectral analysis.

    Computes valence (happy/sad), arousal (calm/energetic), tension, and warmth
    from spectral features, then maps to mood labels.
    """
    # --- Valence (brightness + mode + harmonic content) ---
    try:
        # Spectral centroid = perceived brightness
        cent = float(np.mean(librosa.feature.spectral_centroid(y=y, sr=sr)))
        brightness_val = min(1.0, cent / 6000)  # normalize

        # Major keys tend to sound "happier"
        is_major = "major" in key.lower() or key.endswith("B")  # Camelot B = major
        mode_bonus = 0.2 if is_major else -0.15

        # Harmonic richness (tonnetz spread)
        tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
        harmonic_spread = float(np.std(tonnetz))

        valence = (brightness_val - 0.3) * 2 + mode_bonus + harmonic_spread * 0.5
        valence = max(-1.0, min(1.0, valence))
    except Exception:
        valence = 0.0

    # --- Arousal (energy + onset rate + spectral flux) ---
    try:
        rms = librosa.feature.rms(y=y)[0]
        rms_mean = float(np.mean(rms))
        rms_norm = min(1.0, rms_mean / 0.2)

        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_rate = float(np.mean(onset_env))
        onset_norm = min(1.0, onset_rate / 3.0)

        # Spectral flux (rate of spectral change)
        spec = np.abs(librosa.stft(y))
        flux = np.sqrt(np.mean(np.diff(spec, axis=1) ** 2))
        flux_norm = min(1.0, flux / 5.0)

        arousal = (rms_norm * 0.4 + onset_norm * 0.35 + flux_norm * 0.25) * 2 - 1
        arousal = max(-1.0, min(1.0, arousal))
    except Exception:
        arousal = (energy_level - 5) / 5.0

    # --- Tension (dissonance + spectral irregularity + high-freq energy) ---
    try:
        # Spectral flatness (noise-like = more tension)
        flat = float(np.mean(librosa.feature.spectral_flatness(y=y)))

        # High frequency energy ratio
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=32)
        mel_db = librosa.power_to_db(mel, ref=np.max)
        high_energy = float(np.mean(mel_db[24:]))  # top quarter
        total_energy = float(np.mean(mel_db))
        hf_ratio = max(0, (high_energy - total_energy + 20) / 40)

        # Chromagram entropy (harmonic complexity/dissonance)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_entropy = float(np.mean(-np.sum(
            chroma * np.log2(chroma + 1e-8), axis=0
        )))
        dissonance = chroma_entropy / 3.58  # max entropy for 12 bins

        tension = flat * 0.3 + hf_ratio * 0.3 + dissonance * 0.4
        tension = max(0.0, min(1.0, tension))
    except Exception:
        tension = 0.3

    # --- Warmth (low-mid presence, spectral tilt, reverb estimate) ---
    try:
        mel = librosa.feature.melspectrogram(y=y, sr=sr, n_mels=32)
        mel_db = librosa.power_to_db(mel, ref=np.max)
        low_mid = float(np.mean(mel_db[4:12]))   # ~200-1500 Hz
        high_mid = float(np.mean(mel_db[16:24]))  # ~2000-6000 Hz
        warmth_raw = (low_mid - high_mid + 10) / 20
        warmth = max(0.0, min(1.0, warmth_raw))
    except Exception:
        warmth = 0.5

    # --- Map to mood label ---
    best_mood = "neutral"
    best_fit = 0.0

    for label, ranges in _MOOD_LABELS.items():
        v_lo, v_hi = ranges["valence"]
        a_lo, a_hi = ranges["arousal"]
        t_lo, t_hi = ranges["tension"]

        # How well does our detected mood match this label?
        v_fit = 1.0 if v_lo <= valence <= v_hi else max(0, 1 - min(abs(valence - v_lo), abs(valence - v_hi)))
        a_fit = 1.0 if a_lo <= arousal <= a_hi else max(0, 1 - min(abs(arousal - a_lo), abs(arousal - a_hi)))
        t_fit = 1.0 if t_lo <= tension <= t_hi else max(0, 1 - min(abs(tension - t_lo), abs(tension - t_hi)))

        fit = v_fit * 0.35 + a_fit * 0.4 + t_fit * 0.25
        if fit > best_fit:
            best_fit = fit
            best_mood = label

    # Generate descriptive tags
    tags = [best_mood]
    if valence > 0.4:
        tags.append("bright")
    elif valence < -0.3:
        tags.append("dark")
    if arousal > 0.4:
        tags.append("driving")
    elif arousal < -0.3:
        tags.append("laid-back")
    if tension > 0.6:
        tags.append("intense")
    if warmth > 0.6:
        tags.append("warm")
    elif warmth < 0.3:
        tags.append("cold")

    return MoodProfile(
        primary=best_mood,
        confidence=round(best_fit, 3),
        valence=round(valence, 3),
        arousal=round(arousal, 3),
        tension=round(tension, 3),
        warmth=round(warmth, 3),
        tags=tags,
    )


# ---------------------------------------------------------------------------
# 4. Smart Transition Points — detect drops, breakdowns, builds
# ---------------------------------------------------------------------------

@dataclass
class StructuralMarkers:
    """Musical structure detected from audio: drops, breakdowns, builds."""
    drops: list[float]         # seconds where energy drops hit
    breakdowns: list[float]    # seconds where breakdowns begin
    builds: list[float]        # seconds where energy builds start
    phrase_boundaries: list[float]  # all detected phrase start times

    def to_dict(self) -> dict:
        return {
            "drops": [round(t, 2) for t in self.drops],
            "breakdowns": [round(t, 2) for t in self.breakdowns],
            "builds": [round(t, 2) for t in self.builds],
            "phrase_boundaries": [round(t, 2) for t in self.phrase_boundaries],
        }


def detect_structure(y: np.ndarray, sr: int, bpm: float) -> StructuralMarkers:
    """Detect musical structure (drops, breakdowns, builds) from audio.

    Uses spectral flux, onset strength, and energy envelope to identify
    key structural moments in the track.
    """
    if bpm <= 0:
        bpm = 128.0

    beat_dur = 60.0 / bpm
    phrase_dur = beat_dur * 16  # 16-beat phrases
    duration = librosa.get_duration(y=y, sr=sr)

    # Compute energy envelope with high resolution
    hop = max(1, int(sr * 0.1))  # 100ms windows
    rms = librosa.feature.rms(y=y, hop_length=hop)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    if len(rms) < 10:
        return StructuralMarkers([], [], [], [])

    # Smooth energy
    kernel_size = max(3, int(1.0 / 0.1))  # 1-second smoothing
    kernel = np.ones(kernel_size) / kernel_size
    rms_smooth = np.convolve(rms, kernel, mode="same")
    rms_norm = rms_smooth / (np.max(rms_smooth) + 1e-8)

    # Energy derivative (rate of change)
    energy_diff = np.diff(rms_norm)
    diff_times = times[:-1]

    # Onset strength for percussive analysis
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
        if len(onset_env) > len(rms_norm):
            onset_env = onset_env[:len(rms_norm)]
        elif len(onset_env) < len(rms_norm):
            onset_env = np.pad(onset_env, (0, len(rms_norm) - len(onset_env)))
    except Exception:
        onset_env = rms_norm

    drops = []
    breakdowns = []
    builds = []
    phrase_boundaries = []

    # Detect phrase boundaries (every 16 beats, snapped to energy peaks)
    t = phrase_dur
    while t < duration - phrase_dur:
        phrase_boundaries.append(t)
        t += phrase_dur

    # Detect structural elements by analyzing energy derivative in phrases
    for i in range(len(phrase_boundaries) - 1):
        start_t = phrase_boundaries[i]
        end_t = phrase_boundaries[i + 1]

        # Get energy values in this phrase
        mask = (times >= start_t) & (times < end_t)
        phrase_energy = rms_norm[mask]
        if len(phrase_energy) < 3:
            continue

        avg_energy = float(np.mean(phrase_energy))
        energy_change = float(phrase_energy[-1] - phrase_energy[0])

        # Get previous phrase energy for comparison
        if i > 0:
            prev_start = phrase_boundaries[i - 1]
            prev_mask = (times >= prev_start) & (times < start_t)
            prev_energy = float(np.mean(rms_norm[prev_mask])) if np.any(prev_mask) else avg_energy
        else:
            prev_energy = avg_energy

        energy_jump = avg_energy - prev_energy

        # DROP: sudden energy increase after a low-energy section
        if energy_jump > 0.25 and prev_energy < 0.5:
            drops.append(start_t)

        # BREAKDOWN: significant energy decrease
        elif energy_jump < -0.2 and avg_energy < 0.5:
            breakdowns.append(start_t)

        # BUILD: sustained energy increase within the phrase
        elif energy_change > 0.15 and avg_energy > prev_energy:
            builds.append(start_t)

    return StructuralMarkers(
        drops=drops,
        breakdowns=breakdowns,
        builds=builds,
        phrase_boundaries=phrase_boundaries,
    )


# ---------------------------------------------------------------------------
# 5. AI Transition Scoring — how well two tracks mesh sonically
# ---------------------------------------------------------------------------

def score_sonic_compatibility(
    emb_a: list[float],
    emb_b: list[float],
    mood_a: dict,
    mood_b: dict,
) -> tuple[float, str]:
    """Score how well two tracks will sound together based on their
    audio embeddings and mood profiles.

    Goes beyond key/BPM matching to evaluate timbral similarity,
    mood continuity, and spectral compatibility.

    Returns (score 0-1, explanation).
    """
    parts = []

    # Timbral similarity from embeddings
    timbre_sim = embedding_similarity(emb_a, emb_b)
    # Map from [-1, 1] to [0, 1], with bias toward positive similarity
    timbre_score = max(0, min(1, (timbre_sim + 0.5) / 1.5))
    parts.append(f"Timbre: {timbre_score:.0%}")

    # Mood continuity — similar mood dimensions = smoother transition
    try:
        v_diff = abs(mood_a.get("valence", 0) - mood_b.get("valence", 0))
        a_diff = abs(mood_a.get("arousal", 0) - mood_b.get("arousal", 0))
        t_diff = abs(mood_a.get("tension", 0) - mood_b.get("tension", 0))
        w_diff = abs(mood_a.get("warmth", 0) - mood_b.get("warmth", 0))

        # Allow some arousal change (energy progression) but penalize
        # large valence/tension jumps (jarring mood shifts)
        mood_score = 1.0 - (v_diff * 0.35 + a_diff * 0.15 + t_diff * 0.3 + w_diff * 0.2)
        mood_score = max(0, min(1, mood_score))
    except Exception:
        mood_score = 0.5

    if mood_score > 0.7:
        parts.append("Mood flows naturally")
    elif mood_score < 0.4:
        parts.append("Mood shift — could be jarring")

    # Combined score
    overall = timbre_score * 0.55 + mood_score * 0.45

    return round(overall, 3), " | ".join(parts)


# ---------------------------------------------------------------------------
# Convenience: run all intelligence analysis on loaded audio
# ---------------------------------------------------------------------------

def analyze_intelligence(
    y: np.ndarray,
    sr: int,
    bpm: float,
    brightness: float,
    energy_level: int,
    has_vocals: bool,
    key: str = "",
) -> dict:
    """Run all AI analysis on a loaded audio track.

    Returns dict with keys: ai_genre, ai_genre_confidence, mood, embedding, structure
    """
    # Genre
    ai_genre, ai_genre_conf = classify_genre(y, sr, bpm, brightness, energy_level, has_vocals)

    # Mood
    mood = detect_mood(y, sr, key, energy_level)

    # Embedding
    embedding = compute_audio_embedding(y, sr)

    # Structure
    structure = detect_structure(y, sr, bpm)

    return {
        "ai_genre": ai_genre,
        "ai_genre_confidence": ai_genre_conf,
        "mood": mood.to_dict(),
        "embedding": embedding,
        "structure": structure.to_dict(),
    }
