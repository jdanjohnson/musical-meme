"""Core audio analysis — BPM, key, energy detection using librosa."""

import hashlib
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
    format: str
    sample_rate: int
    channels: int
    analyzed_at: str
    file_modified_at: str

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
    """Detect BPM using librosa's beat tracker.

    Returns (bpm, confidence).
    """
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    bpm = float(np.atleast_1d(tempo)[0])

    # Confidence based on beat regularity
    if len(beat_frames) < 4:
        return bpm, 0.3

    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    intervals = np.diff(beat_times)
    if len(intervals) > 0:
        cv = np.std(intervals) / (np.mean(intervals) + 1e-8)
        confidence = max(0.0, min(1.0, 1.0 - cv))
    else:
        confidence = 0.3

    return round(bpm, 1), round(confidence, 3)


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


def infer_genre_from_path(filepath: str, root_folder: str | None = None) -> str | None:
    """Infer genre from folder structure.

    If root_folder is given, use the first subfolder as genre.
    Otherwise use the parent folder name.
    """
    path = Path(filepath)
    if root_folder:
        root = Path(root_folder)
        try:
            relative = path.relative_to(root)
            parts = relative.parts
            if len(parts) > 1:
                return parts[0]
        except ValueError:
            pass
    return path.parent.name


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

    # Genre from folder
    genre = infer_genre_from_path(filepath, root_folder)

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
        format=path.suffix.lstrip(".").upper(),
        sample_rate=sample_rate,
        channels=channels,
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        file_modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    )
