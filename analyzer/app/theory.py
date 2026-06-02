"""Music theory engine — Camelot wheel, harmonic compatibility, energy scoring."""

from dataclasses import dataclass

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

    Returns (score, explanation).
    """
    # Define target energy at each position (standard arc)
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

    if delta <= 1:
        score = 1.0
        explanation = f"Energy {candidate_energy} fits arc target {target:.0f} perfectly"
    elif delta <= 2:
        score = 0.8
        explanation = f"Energy {candidate_energy} close to arc target {target:.0f}"
    elif delta <= 3:
        score = 0.6
        explanation = f"Energy {candidate_energy} slightly off arc target {target:.0f}"
    else:
        score = max(0.1, 0.5 - delta * 0.08)
        explanation = f"Energy {candidate_energy} far from arc target {target:.0f}"

    # Bonus for matching expected direction
    if position_in_set < 0.6 and direction > 0:
        score = min(1.0, score + 0.1)
        explanation += " (building energy — good)"
    elif position_in_set > 0.85 and direction < 0:
        score = min(1.0, score + 0.1)
        explanation += " (winding down — good)"

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
    """Score a transition between two tracks on all dimensions."""
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

    # Weighted overall
    overall = 0.45 * h_score + 0.25 * b_score + 0.30 * e_score

    # Build explanation
    parts = [h_move]
    if bpm_delta > 0:
        parts.append(f"BPM: {track_a.get('bpm', '?')}→{track_b.get('bpm', '?')} (Δ{bpm_delta:.1f})")
    parts.append(e_explanation)

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
    First track has None score.
    """
    pool = all_tracks
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

    while total_duration < target_minutes and len(used_ids) < len(pool):
        position = min(1.0, total_duration / target_minutes)
        suggestions = suggest_next_tracks(
            current, pool, position, arc_type, bpm_range, used_ids, limit=5
        )

        if not suggestions:
            break

        next_track, score = suggestions[0]
        result.append((next_track, score))
        used_ids.add(next_track["id"])
        total_duration += next_track.get("duration", 300) / 60
        current = next_track

    return result
