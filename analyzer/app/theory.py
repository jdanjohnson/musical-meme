"""Music theory engine — Camelot wheel, harmonic compatibility, energy scoring."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Camelot wheel: 1-12 for position, A=minor, B=major
# Adjacent keys (same letter ±1, or same number A↔B) are compatible


@dataclass
class TransitionScore:
    harmonic_score: float      # 0-1, how harmonically compatible
    bpm_score: float           # 0-1, how BPM-compatible
    energy_score: float        # 0-1, how well energy fits the arc
    overall_score: float       # 0-1, weighted combination
    harmonic_move: str         # description of the harmonic relationship
    bpm_delta: float           # absolute BPM difference
    energy_delta: int          # energy level change
    camelot_distance: int      # steps on camelot wheel
    explanation: str           # human-readable explanation


def parse_camelot(code: str) -> tuple[int, str] | None:
    """Parse '8A' into (8, 'A'). Returns None if invalid."""
    if not code or len(code) < 2:
        return None
    try:
        letter = code[-1].upper()
        number = int(code[:-1])
        if letter not in ("A", "B") or number < 1 or number > 12:
            return None
        return (number, letter)
    except ValueError:
        return None


def camelot_distance(code1: str, code2: str) -> int:
    """Minimum steps between two Camelot codes on the wheel (0-6)."""
    p1 = parse_camelot(code1)
    p2 = parse_camelot(code2)
    if not p1 or not p2:
        return 12  # unknown = max distance

    n1, l1 = p1
    n2, l2 = p2

    # Circular distance on 1-12 wheel
    num_dist = min(abs(n1 - n2), 12 - abs(n1 - n2))

    if l1 == l2:
        return num_dist
    else:
        # Mode switch (A↔B) at same number = 0 distance, otherwise combine
        return num_dist  # simplified: mode switches add color, not distance


def harmonic_relationship(code1: str, code2: str) -> tuple[float, str]:
    """Score harmonic compatibility (0-1) and describe the relationship.

    Returns (score, description).
    """
    p1 = parse_camelot(code1)
    p2 = parse_camelot(code2)
    if not p1 or not p2:
        return 0.3, "Unknown key"

    n1, l1 = p1
    n2, l2 = p2

    # Circular number distance
    num_dist = min(abs(n1 - n2), 12 - abs(n1 - n2))
    # Direction: positive = clockwise
    clockwise = (n2 - n1) % 12
    counter = (n1 - n2) % 12

    # Same key
    if n1 == n2 and l1 == l2:
        return 1.0, "Same key — perfect match"

    # Mode switch (same number, A↔B)
    if n1 == n2 and l1 != l2:
        return 0.95, "Mode switch (minor↔major) — mood flip, smooth"

    # Adjacent same letter (±1)
    if l1 == l2 and num_dist == 1:
        if clockwise == 1:
            return 0.9, "Clockwise +1 — energy lift"
        else:
            return 0.9, "Counter-clockwise −1 — energy release"

    # ±2 same letter
    if l1 == l2 and num_dist == 2:
        if clockwise == 2:
            return 0.7, "+2 Camelot — noticeable energy boost"
        else:
            return 0.7, "−2 Camelot — noticeable energy drop"

    # Dominant jump (+7, like V→I in classical)
    if l1 == l2 and clockwise == 7:
        return 0.65, "Dominant jump (+7) — bold resolution"

    # Subdominant (-7 / +5)
    if l1 == l2 and counter == 7:
        return 0.6, "Subdominant jump (−7) — warm shift"

    # ±1 with mode switch
    if l1 != l2 and num_dist == 1:
        return 0.75, "Adjacent + mode switch — complex but musical"

    # Tritone (±6)
    if num_dist == 6:
        return 0.3, "Tritone (±6) — maximum tension, use at peaks/resets"

    # 3-5 steps
    if num_dist <= 3:
        return 0.5, f"±{num_dist} Camelot — moderate harmonic shift"
    if num_dist <= 5:
        return 0.35, f"±{num_dist} Camelot — significant key change"

    return 0.2, f"±{num_dist} Camelot — distant, use intentionally"


def bpm_compatibility(bpm1: float, bpm2: float, max_delta: float = 8.0) -> tuple[float, float]:
    """Score BPM compatibility (0-1) and return the delta.

    Also considers half/double time relationships.
    """
    if bpm1 <= 0 or bpm2 <= 0:
        return 0.5, 0.0

    delta = abs(bpm1 - bpm2)

    # Check half/double time
    half_delta = abs(bpm1 - bpm2 / 2)
    double_delta = abs(bpm1 - bpm2 * 2)
    effective_delta = min(delta, half_delta, double_delta)

    if effective_delta <= 1:
        return 1.0, delta
    elif effective_delta <= 3:
        return 0.9, delta
    elif effective_delta <= max_delta:
        score = 1.0 - (effective_delta - 1) / (max_delta - 1) * 0.5
        return round(score, 2), delta
    else:
        score = max(0.1, 0.5 - (effective_delta - max_delta) / 20)
        return round(score, 2), delta


def energy_arc_fit(
    current_energy: int,
    candidate_energy: int,
    position_in_set: float,  # 0.0 (start) to 1.0 (end)
    arc_type: str = "standard",
) -> tuple[float, str]:
    """Score how well a candidate track's energy fits the arc at this position.

    Uses continuous scoring (not just buckets) so that a track at exactly the
    target energy scores higher than one that's 0.9 levels away. Also penalizes
    staying at the same energy for too long and rewards movement toward the target.

    Returns (score, explanation).
    """
    arcs = {
        "standard": _standard_arc,
        "warmup_peak": _warmup_peak_arc,
        "peak_sustain": _peak_sustain_arc,
        "journey": _journey_arc,
        "flat": lambda p: 5,
        "pride_night": _pride_night_arc,
        "sexy_groovy": _sexy_groovy_arc,
        "long_build": _long_build_arc,
    }

    arc_fn = arcs.get(arc_type, _standard_arc)
    target = arc_fn(position_in_set)

    delta = abs(candidate_energy - target)
    direction = candidate_energy - current_energy

    # Continuous scoring: exponential decay from target
    # delta 0 → 1.0, delta 1 → 0.85, delta 2 → 0.65, delta 3 → 0.45, delta 4+ → low
    score = max(0.05, 1.0 * (0.85 ** delta))

    if delta < 0.5:
        explanation = f"Energy {candidate_energy} hits arc target {target:.0f}"
    elif delta <= 1.5:
        explanation = f"Energy {candidate_energy} near arc target {target:.0f}"
    elif delta <= 2.5:
        explanation = f"Energy {candidate_energy} slightly off arc target {target:.0f}"
    else:
        explanation = f"Energy {candidate_energy} far from arc target {target:.0f}"

    # Penalize staying flat — if current and candidate are the same energy,
    # reduce score slightly to encourage movement
    if abs(direction) == 0 and arc_type != "flat":
        score *= 0.85
        explanation += " (flat — no energy movement)"

    # Bonus for moving toward target direction
    target_direction = target - current_energy
    if target_direction > 0.5 and direction > 0:
        score = min(1.0, score * 1.15)
        explanation += " (building energy — good)"
    elif target_direction < -0.5 and direction < 0:
        score = min(1.0, score * 1.15)
        explanation += " (winding down — good)"
    elif abs(target_direction) > 1.5 and direction * target_direction < 0:
        # Moving away from where the arc wants to go
        score *= 0.75
        explanation += " (wrong direction for arc)"

    return round(score, 2), explanation


def _standard_arc(position: float) -> float:
    """Standard opener→build→peak→resolution arc."""
    if position < 0.2:
        return 3 + position / 0.2 * 2          # 3→5
    elif position < 0.5:
        return 5 + (position - 0.2) / 0.3 * 3  # 5→8
    elif position < 0.8:
        return 8 + (position - 0.5) / 0.3 * 2  # 8→10
    else:
        return 10 - (position - 0.8) / 0.2 * 4  # 10→6


def _warmup_peak_arc(position: float) -> float:
    """Long warmup, sharp peak."""
    if position < 0.6:
        return 3 + position / 0.6 * 4
    elif position < 0.8:
        return 7 + (position - 0.6) / 0.2 * 3
    else:
        return 10 - (position - 0.8) / 0.2 * 5


def _peak_sustain_arc(position: float) -> float:
    """Quick build, sustained peak."""
    if position < 0.2:
        return 4 + position / 0.2 * 4
    elif position < 0.8:
        return 8 + (position - 0.2) / 0.6 * 2
    else:
        return 10 - (position - 0.8) / 0.2 * 4


def _journey_arc(position: float) -> float:
    """Multiple peaks and valleys — a journey."""
    import math
    base = 5 + 3 * math.sin(position * math.pi * 3)
    # Envelope: start low, end medium
    envelope = 0.5 + 0.5 * math.sin(position * math.pi)
    return max(2, min(10, base * envelope + 2))


def _pride_night_arc(position: float) -> float:
    """4-hour pride night: groovy warmup → steady build → euphoric peak → powerful close.

    9-10pm (0.0-0.25): Sexy, groovy warmup — energy 3-5
    10-11pm (0.25-0.5): Building the vibe — energy 5-7
    11-12am (0.5-0.75): Peak dance floor — energy 7-9
    12-1am (0.75-1.0): Euphoric close — energy 8-10
    """
    if position < 0.25:
        return 3 + position / 0.25 * 2              # 3→5
    elif position < 0.5:
        return 5 + (position - 0.25) / 0.25 * 2      # 5→7
    elif position < 0.75:
        return 7 + (position - 0.5) / 0.25 * 2       # 7→9
    else:
        return 9 + (position - 0.75) / 0.25 * 1      # 9→10


def _sexy_groovy_arc(position: float) -> float:
    """Consistent groove with late peak — keeps it sexy all night."""
    if position < 0.3:
        return 4 + position / 0.3 * 2                 # 4→6
    elif position < 0.7:
        return 6 + (position - 0.3) / 0.4 * 1.5       # 6→7.5
    elif position < 0.9:
        return 7.5 + (position - 0.7) / 0.2 * 2.5     # 7.5→10
    else:
        return 10 - (position - 0.9) / 0.1 * 2        # 10→8


def _long_build_arc(position: float) -> float:
    """Very gradual build for long sets (3-5 hours)."""
    if position < 0.7:
        return 3 + position / 0.7 * 5                  # 3→8
    elif position < 0.9:
        return 8 + (position - 0.7) / 0.2 * 2          # 8→10
    else:
        return 10 - (position - 0.9) / 0.1 * 3         # 10→7


def _custom_time_block_arc(position: float, blocks: list[dict]) -> float:
    """Build energy from custom time blocks.

    blocks: [{"start": 0.0, "end": 0.25, "energy_start": 3, "energy_end": 5}, ...]
    """
    for block in blocks:
        if block["start"] <= position < block["end"]:
            t = (position - block["start"]) / (block["end"] - block["start"])
            return block["energy_start"] + t * (block["energy_end"] - block["energy_start"])
    return blocks[-1]["energy_end"] if blocks else 5


def score_transition(
    track_a: dict,
    track_b: dict,
    position_in_set: float = 0.5,
    arc_type: str = "standard",
    bpm_max_delta: float = 8.0,
) -> TransitionScore:
    """Score a transition between two tracks on all dimensions.

    When AI intelligence data is available (embeddings, mood), incorporates
    sonic compatibility into the overall score for better-sounding transitions.
    """
    # Harmonic
    h_score, h_move = harmonic_relationship(
        track_a.get("camelot", ""), track_b.get("camelot", "")
    )

    # BPM
    b_score, bpm_delta = bpm_compatibility(
        track_a.get("bpm", 0), track_b.get("bpm", 0), bpm_max_delta
    )

    # Energy arc
    e_score, e_explanation = energy_arc_fit(
        track_a.get("energy_level", 5),
        track_b.get("energy_level", 5),
        position_in_set,
        arc_type,
    )

    energy_delta = (track_b.get("energy_level", 5) - track_a.get("energy_level", 5))

    # AI sonic compatibility (if embeddings available)
    sonic_score = 0.0
    sonic_explanation = ""
    has_sonic = False
    emb_a = track_a.get("audio_embedding")
    emb_b = track_b.get("audio_embedding")
    if emb_a and emb_b:
        try:
            import json as _json
            from app.intelligence import score_sonic_compatibility
            ea = _json.loads(emb_a) if isinstance(emb_a, str) else emb_a
            eb = _json.loads(emb_b) if isinstance(emb_b, str) else emb_b
            mood_a = {
                "valence": track_a.get("mood_valence", 0),
                "arousal": track_a.get("mood_arousal", 0),
                "tension": track_a.get("mood_tension", 0),
                "warmth": track_a.get("mood_warmth", 0),
            }
            mood_b = {
                "valence": track_b.get("mood_valence", 0),
                "arousal": track_b.get("mood_arousal", 0),
                "tension": track_b.get("mood_tension", 0),
                "warmth": track_b.get("mood_warmth", 0),
            }
            if ea and eb:
                sonic_score, sonic_explanation = score_sonic_compatibility(ea, eb, mood_a, mood_b)
                has_sonic = True
        except Exception:
            pass

    # Weighted overall — include sonic score when available
    if has_sonic:
        overall = 0.30 * h_score + 0.15 * b_score + 0.25 * e_score + 0.30 * sonic_score
    else:
        overall = 0.45 * h_score + 0.25 * b_score + 0.30 * e_score

    # Build explanation
    parts = [h_move]
    if bpm_delta > 0:
        parts.append(f"BPM: {track_a.get('bpm', '?')}→{track_b.get('bpm', '?')} (Δ{bpm_delta:.1f})")
    parts.append(e_explanation)
    if sonic_explanation:
        parts.append(sonic_explanation)

    return TransitionScore(
        harmonic_score=round(h_score, 2),
        bpm_score=round(b_score, 2),
        energy_score=round(e_score, 2),
        overall_score=round(overall, 2),
        harmonic_move=h_move,
        bpm_delta=round(bpm_delta, 1),
        energy_delta=energy_delta,
        camelot_distance=camelot_distance(
            track_a.get("camelot", ""), track_b.get("camelot", "")
        ),
        explanation=" | ".join(parts),
    )


def suggest_next_tracks(
    current_track: dict,
    all_tracks: list[dict],
    position_in_set: float = 0.5,
    arc_type: str = "standard",
    bpm_range: float = 8.0,
    exclude_ids: set[int] | None = None,
    limit: int = 20,
) -> list[tuple[dict, TransitionScore]]:
    """Suggest the best next tracks from the library.

    Returns list of (track, score) sorted by overall_score descending.
    """
    exclude = exclude_ids or set()
    candidates = []

    for track in all_tracks:
        if track["id"] in exclude or track["id"] == current_track.get("id"):
            continue
        score = score_transition(
            current_track, track, position_in_set, arc_type, bpm_range
        )
        candidates.append((track, score))

    candidates.sort(key=lambda x: x[1].overall_score, reverse=True)
    return candidates[:limit]


_TRAILING_SUFFIX = re.compile(r"[\s_\-\.]*(?:\(\d+\)|\d+)$")


def normalize_track_name(filename: str) -> str:
    """Strip extension and trailing number suffixes for duplicate detection.

    'hey_1.mp3' -> 'hey', 'song (2).wav' -> 'song', 'track-03.mp3' -> 'track'
    """
    stem = Path(filename).stem.lower().strip()
    return _TRAILING_SUFFIX.sub("", stem).strip()


def deduplicate_tracks(tracks: list[dict]) -> list[dict]:
    """Remove near-duplicate tracks, keeping the one with the longest duration.

    Two tracks are considered duplicates if their filenames normalize to the
    same string after stripping extensions and trailing number suffixes.
    """
    groups: dict[str, list[dict]] = {}
    for t in tracks:
        key = normalize_track_name(t.get("filename", ""))
        if not key:
            key = str(t.get("id", ""))
        groups.setdefault(key, []).append(t)

    result = []
    for group in groups.values():
        # Keep the track with the longest duration (most complete version)
        best = max(group, key=lambda t: t.get("duration", 0))
        result.append(best)

    return result


_VIBE_KEYWORDS: dict[str, dict] = {
    # Energy keywords -> target energy range (1-10)
    "chill": {"energy": (1, 4), "bpm": (80, 115)},
    "mellow": {"energy": (1, 4), "bpm": (80, 115)},
    "relaxed": {"energy": (1, 4), "bpm": (80, 110)},
    "laid back": {"energy": (1, 4), "bpm": (80, 110)},
    "calm": {"energy": (1, 3), "bpm": (70, 105)},
    "ambient": {"energy": (1, 3), "bpm": (60, 100)},
    "downtempo": {"energy": (1, 4), "bpm": (70, 110)},
    "lounge": {"energy": (2, 5), "bpm": (85, 115)},
    "warm": {"energy": (3, 6), "bpm": (95, 125)},
    "groovy": {"energy": (4, 7), "bpm": (110, 130)},
    "funky": {"energy": (4, 7), "bpm": (110, 130)},
    "sexy": {"energy": (3, 6), "bpm": (95, 125)},
    "deep": {"energy": (3, 6), "bpm": (115, 128)},
    "underground": {"energy": (4, 7), "bpm": (118, 132)},
    "driving": {"energy": (5, 8), "bpm": (120, 138)},
    "upbeat": {"energy": (5, 8), "bpm": (118, 135)},
    "energetic": {"energy": (6, 9), "bpm": (120, 140)},
    "high energy": {"energy": (7, 10), "bpm": (125, 145)},
    "hype": {"energy": (7, 10), "bpm": (125, 150)},
    "bangers": {"energy": (7, 10), "bpm": (125, 150)},
    "peak time": {"energy": (7, 10), "bpm": (125, 140)},
    "peak": {"energy": (7, 10), "bpm": (125, 140)},
    "festival": {"energy": (7, 10), "bpm": (125, 150)},
    "rave": {"energy": (7, 10), "bpm": (130, 160)},
    "hard": {"energy": (8, 10), "bpm": (135, 160)},
    "intense": {"energy": (8, 10), "bpm": (130, 155)},
    "dark": {"energy": (5, 8), "bpm": (118, 135)},
    "moody": {"energy": (3, 6), "bpm": (105, 128)},
    "dreamy": {"energy": (2, 5), "bpm": (90, 120)},
    "ethereal": {"energy": (2, 5), "bpm": (85, 120)},
    "euphoric": {"energy": (6, 9), "bpm": (125, 140)},
    "uplifting": {"energy": (5, 8), "bpm": (120, 138)},
    "emotional": {"energy": (4, 7), "bpm": (110, 135)},
    "nostalgic": {"energy": (3, 6), "bpm": (100, 128)},
    "summer": {"energy": (4, 7), "bpm": (110, 130)},
    "sunset": {"energy": (3, 6), "bpm": (100, 125)},
    "sunrise": {"energy": (3, 6), "bpm": (110, 128)},
    "after hours": {"energy": (3, 6), "bpm": (115, 130)},
    "late night": {"energy": (4, 7), "bpm": (118, 132)},
    "morning": {"energy": (3, 6), "bpm": (110, 128)},
    "pool party": {"energy": (5, 8), "bpm": (115, 132)},
    "beach": {"energy": (4, 7), "bpm": (105, 128)},
    "club": {"energy": (5, 8), "bpm": (120, 135)},
    "opening": {"energy": (2, 5), "bpm": (110, 125)},
    "closing": {"energy": (3, 6), "bpm": (115, 130)},
    "warmup": {"energy": (2, 5), "bpm": (110, 125)},
    "warm up": {"energy": (2, 5), "bpm": (110, 125)},
    "pride": {"energy": (6, 9), "bpm": (120, 135)},
    "disco": {"energy": (5, 8), "bpm": (115, 130)},
    "house": {"energy": (4, 7), "bpm": (118, 132)},
    "techno": {"energy": (5, 8), "bpm": (125, 145)},
    "minimal": {"energy": (3, 6), "bpm": (118, 132)},
    "progressive": {"energy": (4, 7), "bpm": (122, 135)},
    "trance": {"energy": (5, 8), "bpm": (130, 145)},
    "melodic": {"energy": (4, 7), "bpm": (118, 135)},
    "afro": {"energy": (5, 8), "bpm": (118, 132)},
    "latin": {"energy": (5, 8), "bpm": (105, 128)},
    "r&b": {"energy": (3, 6), "bpm": (85, 115)},
    "hip hop": {"energy": (4, 7), "bpm": (85, 115)},
    "rap": {"energy": (4, 7), "bpm": (80, 110)},
    "trap": {"energy": (5, 8), "bpm": (130, 160)},
    "drum and bass": {"energy": (6, 9), "bpm": (160, 180)},
    "dnb": {"energy": (6, 9), "bpm": (160, 180)},
    "jungle": {"energy": (6, 9), "bpm": (155, 175)},
    "garage": {"energy": (4, 7), "bpm": (128, 140)},
    "uk garage": {"energy": (4, 7), "bpm": (128, 140)},
    "indie": {"energy": (3, 6), "bpm": (100, 130)},
    "rock": {"energy": (5, 8), "bpm": (110, 140)},
    "pop": {"energy": (4, 7), "bpm": (100, 130)},
    "electronic": {"energy": (4, 7), "bpm": (115, 135)},
    "vocal": {"energy": (4, 7), "vocals": True},
    "vocals": {"energy": (4, 7), "vocals": True},
    "instrumental": {"energy": (3, 7), "vocals": False},
    "no vocals": {"energy": (3, 7), "vocals": False},
}


def parse_vibe(description: str) -> dict:
    """Parse a natural-language vibe description into target track attributes.

    Returns {energy_range: (lo, hi), bpm_range: (lo, hi), vocals: bool|None,
             genre_hints: [str], raw: str}
    """
    desc = description.lower().strip()
    energy_ranges = []
    bpm_ranges = []
    vocals = None
    genre_hints = []

    # Match keywords (longest first to handle multi-word matches like "high energy")
    sorted_keywords = sorted(_VIBE_KEYWORDS.keys(), key=len, reverse=True)
    matched = set()
    for kw in sorted_keywords:
        if kw in desc and kw not in matched:
            attrs = _VIBE_KEYWORDS[kw]
            if "energy" in attrs:
                energy_ranges.append(attrs["energy"])
            if "bpm" in attrs:
                bpm_ranges.append(attrs["bpm"])
            if "vocals" in attrs:
                vocals = attrs["vocals"]
            matched.add(kw)

    # Merge ranges: take intersection
    if energy_ranges:
        energy_lo = max(r[0] for r in energy_ranges)
        energy_hi = min(r[1] for r in energy_ranges)
        if energy_lo > energy_hi:
            energy_lo, energy_hi = min(r[0] for r in energy_ranges), max(r[1] for r in energy_ranges)
        energy_range = (energy_lo, energy_hi)
    else:
        energy_range = (1, 10)

    if bpm_ranges:
        bpm_lo = max(r[0] for r in bpm_ranges)
        bpm_hi = min(r[1] for r in bpm_ranges)
        if bpm_lo > bpm_hi:
            bpm_lo, bpm_hi = min(r[0] for r in bpm_ranges), max(r[1] for r in bpm_ranges)
        bpm_range = (bpm_lo, bpm_hi)
    else:
        bpm_range = (60, 200)

    return {
        "energy_range": energy_range,
        "bpm_range": bpm_range,
        "vocals": vocals,
        "keywords_matched": list(matched),
        "raw": description,
    }


def score_track_vibe(track: dict, vibe: dict) -> float:
    """Score how well a track matches a vibe profile (0-1)."""
    score = 0.0
    weights = 0.0

    # Energy match (40% weight)
    energy = track.get("energy_level", 5)
    e_lo, e_hi = vibe["energy_range"]
    if e_lo <= energy <= e_hi:
        # Closer to middle of range = better
        mid = (e_lo + e_hi) / 2
        dist = abs(energy - mid) / max(1, (e_hi - e_lo) / 2)
        score += 0.4 * (1 - dist * 0.3)  # slight penalty for edges
    else:
        dist = min(abs(energy - e_lo), abs(energy - e_hi))
        score += 0.4 * max(0, 1 - dist * 0.25)
    weights += 0.4

    # BPM match (35% weight)
    bpm = track.get("bpm", 120)
    b_lo, b_hi = vibe["bpm_range"]
    if b_lo <= bpm <= b_hi:
        mid = (b_lo + b_hi) / 2
        span = max(1, (b_hi - b_lo) / 2)
        dist = abs(bpm - mid) / span
        score += 0.35 * (1 - dist * 0.2)
    else:
        dist = min(abs(bpm - b_lo), abs(bpm - b_hi))
        score += 0.35 * max(0, 1 - dist * 0.05)
    weights += 0.35

    # Vocal match (15% weight, only if specified)
    if vibe["vocals"] is not None:
        has_vocals = bool(track.get("has_vocals", False))
        if has_vocals == vibe["vocals"]:
            score += 0.15
        else:
            score += 0.03
        weights += 0.15
    else:
        # Redistribute to energy + bpm
        score += 0.15 * (score / max(0.01, weights))
        weights += 0.15

    # Mood-aware scoring (10% weight) — uses AI mood when available
    mood_primary = track.get("mood_primary", "")
    mood_valence = track.get("mood_valence", 0)
    mood_arousal = track.get("mood_arousal", 0)

    if mood_primary:
        # Map vibe keywords to expected mood attributes
        desc_lower = vibe.get("raw", "").lower()
        mood_bonus = 0.0
        # Dark vibes should match dark/aggressive/hypnotic moods
        if any(w in desc_lower for w in ("dark", "underground", "afterhours", "after hours", "late night")):
            if mood_primary in ("dark", "aggressive", "hypnotic"):
                mood_bonus = 1.0
            elif mood_valence < -0.2:
                mood_bonus = 0.6
        # Euphoric/happy vibes should match euphoric/uplifting moods
        elif any(w in desc_lower for w in ("euphoric", "happy", "joyful", "uplifting", "pride")):
            if mood_primary in ("euphoric", "uplifting", "energetic"):
                mood_bonus = 1.0
            elif mood_valence > 0.3:
                mood_bonus = 0.6
        # Chill/relaxed vibes
        elif any(w in desc_lower for w in ("chill", "relax", "calm", "mellow", "sunset", "lounge")):
            if mood_primary in ("chill", "dreamy", "melancholic"):
                mood_bonus = 1.0
            elif mood_arousal < -0.1:
                mood_bonus = 0.6
        # Groovy/funky vibes
        elif any(w in desc_lower for w in ("groovy", "funky", "disco", "sexy", "groove")):
            if mood_primary in ("groovy", "energetic"):
                mood_bonus = 1.0
            elif mood_valence > 0 and mood_arousal > 0:
                mood_bonus = 0.5
        # Intense/driving vibes
        elif any(w in desc_lower for w in ("intense", "driving", "hard", "peak", "banger")):
            if mood_primary in ("energetic", "aggressive"):
                mood_bonus = 1.0
            elif mood_arousal > 0.3:
                mood_bonus = 0.6
        else:
            # Generic: reward tracks whose arousal matches energy target
            target_arousal = (e_lo + e_hi - 10) / 10  # map 1-10 to -1..1
            mood_bonus = max(0, 1 - abs(mood_arousal - target_arousal))

        score += 0.1 * mood_bonus
    else:
        # Fallback: brightness-based scoring
        brightness = track.get("brightness", 0.5)
        target_brightness = (e_lo + e_hi) / 20
        bright_match = 1 - abs(brightness - target_brightness)
        score += 0.1 * max(0, bright_match)

    return min(1.0, score)


def vibe_generate_set(
    all_tracks: list[dict],
    vibe_description: str,
    target_minutes: int = 60,
    bpm_range_override: float = 8.0,
) -> list[tuple[dict, TransitionScore | None]]:
    """Generate a set based on a natural-language vibe description."""
    pool = deduplicate_tracks(all_tracks)
    if not pool:
        return []

    vibe = parse_vibe(vibe_description)

    # Score all tracks against the vibe
    scored = [(t, score_track_vibe(t, vibe)) for t in pool]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Take the top tracks that fit the vibe (at least 50% match)
    vibe_pool = [t for t, s in scored if s >= 0.3]
    if not vibe_pool:
        vibe_pool = [t for t, _ in scored[:20]]

    # Use the best vibe match as opener
    opener = vibe_pool[0]

    # Build the set using the standard algorithm but with the vibe-filtered pool
    result: list[tuple[dict, TransitionScore | None]] = [(opener, None)]
    used_ids = {opener["id"]}
    total_duration = opener.get("duration", 300) / 60

    while total_duration < target_minutes and len(used_ids) < len(vibe_pool):
        position = min(1.0, total_duration / target_minutes)
        suggestions = suggest_next_tracks(
            result[-1][0], vibe_pool, position, "standard", bpm_range_override, used_ids, limit=5
        )

        if not suggestions:
            break

        next_track, score = suggestions[0]
        result.append((next_track, score))
        used_ids.add(next_track["id"])
        total_duration += next_track.get("duration", 300) / 60

    return result


def auto_generate_set(
    all_tracks: list[dict],
    start_track: dict | None = None,
    target_minutes: int = 60,
    arc_type: str = "standard",
    bpm_range: float = 8.0,
    genre_filter: str | None = None,
) -> list[tuple[dict, TransitionScore | None]]:
    """Auto-generate a full DJ set.

    Returns list of (track, transition_score_from_previous).
    First track has None score. Uses key-diversity penalty so the set doesn't
    stay in the same key for too many tracks in a row.
    """
    pool = deduplicate_tracks(all_tracks)
    if genre_filter:
        genre_lower = genre_filter.lower()
        pool = [t for t in pool if (t.get("genre") or "").lower() == genre_lower]

    if not pool:
        return []

    # Pick starting track
    if start_track:
        current = start_track
    else:
        # Pick a good opener: lower energy, neutral key
        openers = sorted(pool, key=lambda t: t.get("energy_level", 5))
        current = openers[len(openers) // 4]  # 25th percentile energy

    result: list[tuple[dict, TransitionScore | None]] = [(current, None)]
    used_ids = {current["id"]}
    total_duration = current.get("duration", 300) / 60  # minutes

    # Track consecutive same-key count for diversity penalty
    consecutive_same_key = 0
    recent_keys: list[str] = [current.get("camelot", "")]

    while total_duration < target_minutes and len(used_ids) < len(pool):
        position = min(1.0, total_duration / target_minutes)
        suggestions = suggest_next_tracks(
            current, pool, position, arc_type, bpm_range, used_ids, limit=15
        )

        if not suggestions:
            break

        # Apply key diversity penalty: after 3+ tracks in the same key,
        # boost tracks that move to a different (but compatible) key
        best_track = None
        best_score = None
        cur_key = current.get("camelot", "")

        for track, score in suggestions:
            adjusted_overall = score.overall_score
            track_key = track.get("camelot", "")

            if track_key == cur_key:
                # Penalize staying in same key after 2+ consecutive tracks
                if consecutive_same_key >= 2:
                    penalty = 0.08 * (consecutive_same_key - 1)
                    adjusted_overall -= min(0.25, penalty)
            else:
                # Reward compatible key change after staying in same key
                if consecutive_same_key >= 2 and score.harmonic_score >= 0.7:
                    adjusted_overall += 0.05

            if best_score is None or adjusted_overall > best_score:
                best_score = adjusted_overall
                best_track = (track, score)

        if best_track is None:
            break

        next_track, score = best_track
        result.append((next_track, score))
        used_ids.add(next_track["id"])
        total_duration += next_track.get("duration", 300) / 60

        # Update key tracking
        next_key = next_track.get("camelot", "")
        if next_key == cur_key:
            consecutive_same_key += 1
        else:
            consecutive_same_key = 0
        recent_keys.append(next_key)

        current = next_track

    return result


def analyze_set_gaps(
    set_tracks: list[dict],
    arc_type: str = "standard",
    target_minutes: int = 60,
) -> list[dict]:
    """Analyze a generated set and identify gaps in the vibe/energy/harmony.

    Returns list of gap descriptions with suggestions for what to find.
    """
    gaps = []

    if len(set_tracks) < 2:
        return gaps

    total_duration = sum(t.get("duration", 300) for t in set_tracks) / 60

    # Check if set is too short for target
    if total_duration < target_minutes * 0.8:
        deficit = target_minutes - total_duration
        gaps.append({
            "type": "duration",
            "severity": "high",
            "position": len(set_tracks),
            "time_in_set": f"{int(total_duration)}min",
            "message": f"Set is {int(deficit)} minutes short of {target_minutes}min target — need more tracks",
            "suggestion": f"Find {int(deficit / 4)} more tracks around {set_tracks[-1].get('bpm', 128):.0f} BPM",
        })

    # Analyze transitions for weak spots
    arcs = {
        "standard": _standard_arc,
        "warmup_peak": _warmup_peak_arc,
        "peak_sustain": _peak_sustain_arc,
        "journey": _journey_arc,
        "flat": lambda p: 5,
        "pride_night": _pride_night_arc,
        "sexy_groovy": _sexy_groovy_arc,
        "long_build": _long_build_arc,
    }
    arc_fn = arcs.get(arc_type, _standard_arc)

    for i in range(1, len(set_tracks)):
        prev = set_tracks[i - 1]
        curr = set_tracks[i]
        position = i / len(set_tracks)
        time_min = sum(t.get("duration", 300) for t in set_tracks[:i]) / 60

        # Energy gap check
        target_energy = arc_fn(position)
        actual_energy = curr.get("energy_level", 5)
        energy_delta = abs(actual_energy - target_energy)

        if energy_delta > 3:
            gaps.append({
                "type": "energy",
                "severity": "high",
                "position": i,
                "time_in_set": f"{int(time_min)}min",
                "message": f"Energy mismatch at position {i + 1}: track is {actual_energy}/10 but arc wants {target_energy:.0f}/10",
                "suggestion": f"Find a track with energy ~{target_energy:.0f} around {curr.get('bpm', 128):.0f} BPM in key {curr.get('camelot', '?')}",
            })

        # Harmonic gap check
        h_score, h_desc = harmonic_relationship(
            prev.get("camelot", ""), curr.get("camelot", "")
        )
        if h_score < 0.4:
            # Find what key would bridge nicely
            prev_cam = parse_camelot(prev.get("camelot", ""))
            curr_cam = parse_camelot(curr.get("camelot", ""))
            bridge_keys = []
            if prev_cam:
                n, l = prev_cam
                bridge_keys.append(f"{n}{l}")
                bridge_keys.append(f"{(n % 12) + 1}{l}")
                bridge_keys.append(f"{n}{'B' if l == 'A' else 'A'}")

            gaps.append({
                "type": "harmonic",
                "severity": "medium",
                "position": i,
                "time_in_set": f"{int(time_min)}min",
                "message": f"Rough key change at position {i + 1}: {prev.get('camelot', '?')} → {curr.get('camelot', '?')} ({h_desc})",
                "suggestion": f"Insert a bridge track in key {' or '.join(bridge_keys[:2])} between these two",
            })

        # BPM jump check
        bpm_delta = abs((prev.get("bpm", 0) or 0) - (curr.get("bpm", 0) or 0))
        if bpm_delta > 15:
            avg_bpm = ((prev.get("bpm", 0) or 0) + (curr.get("bpm", 0) or 0)) / 2
            gaps.append({
                "type": "bpm",
                "severity": "medium",
                "position": i,
                "time_in_set": f"{int(time_min)}min",
                "message": f"BPM jump at position {i + 1}: {prev.get('bpm', 0):.0f} → {curr.get('bpm', 0):.0f} (Δ{bpm_delta:.0f})",
                "suggestion": f"Insert a track around {avg_bpm:.0f} BPM to smooth the transition",
            })

    # Check for energy plateau (same energy for too many tracks in a row)
    streak = 1
    for i in range(1, len(set_tracks)):
        if set_tracks[i].get("energy_level") == set_tracks[i - 1].get("energy_level"):
            streak += 1
        else:
            streak = 1

        if streak >= 4:
            time_min = sum(t.get("duration", 300) for t in set_tracks[:i]) / 60
            energy = set_tracks[i].get("energy_level", 5)
            gaps.append({
                "type": "plateau",
                "severity": "low",
                "position": i,
                "time_in_set": f"{int(time_min)}min",
                "message": f"Energy plateau: {streak} tracks at energy {energy} — crowd may lose interest",
                "suggestion": f"Mix in a track with energy {energy + 2 if energy < 8 else energy - 2} for contrast",
            })
            streak = 1  # Reset after flagging

    return gaps
