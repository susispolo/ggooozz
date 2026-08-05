"""
Similarity engine for comparing audio features.
Computes weighted similarity scores between tracks.
"""
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from audio_analyzer import AudioFeatures
from musicbrainz_client import AcousticBrainzFeatures

log = logging.getLogger(__name__)


@dataclass
class SimilarityResult:
    """Result of similarity comparison."""
    track_id: int
    title: str
    artist: str
    similarity_score: float  # 0.0 to 1.0
    preview_url: str = ""
    album_art: str = ""
    deezer_url: str = ""

    # Breakdown for debugging
    timbre_score: float = 0.0
    tempo_score: float = 0.0
    energy_score: float = 0.0
    valence_score: float = 0.0
    dance_score: float = 0.0


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    dot_product = np.dot(a, b)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot_product / (norm_a * norm_b))


def compare_audio_features(
    features_a: AudioFeatures,
    features_b: AudioFeatures,
) -> float:
    """
    Compare two sets of audio features.
    Returns similarity score from 0.0 (completely different) to 1.0 (identical).
    """
    # Convert to vectors
    vec_a = features_a.to_vector()
    vec_b = features_b.to_vector()

    # Handle zero vectors
    if np.all(vec_a == 0) or np.all(vec_b == 0):
        return 0.0

    # Cosine similarity on full feature vector
    return cosine_similarity(vec_a, vec_b)


def compare_acoustic_features(
    features_a: AcousticBrainzFeatures,
    features_b: AcousticBrainzFeatures,
) -> float:
    """
    Compare two sets of AcousticBrainz features.
    Focuses on high-level features (danceability, energy, valence, mood).
    """
    vec_a = np.array([
        features_a.danceability,
        features_a.energy,
        features_a.valence,
        features_a.acousticness,
        features_a.instrumentalness,
        features_a.mood_happy,
        features_a.mood_sad,
        features_a.mood_aggressive,
        features_a.mood_relaxed,
        features_a.mood_party,
    ], dtype=np.float32)

    vec_b = np.array([
        features_b.danceability,
        features_b.energy,
        features_b.valence,
        features_b.acousticness,
        features_b.instrumentalness,
        features_b.mood_happy,
        features_b.mood_sad,
        features_b.mood_aggressive,
        features_b.mood_relaxed,
        features_b.mood_party,
    ], dtype=np.float32)

    if np.all(vec_a == 0) or np.all(vec_b == 0):
        return 0.0

    return cosine_similarity(vec_a, vec_b)


def compute_weighted_similarity(
    audio_features_a: Optional[AudioFeatures],
    audio_features_b: Optional[AudioFeatures],
    acoustic_features_a: Optional[AcousticBrainzFeatures],
    acoustic_features_b: Optional[AcousticBrainzFeatures],
    lastfm_match: float = 0.0,
) -> tuple[float, dict]:
    """
    Compute weighted similarity score from multiple feature sources.

    Returns:
        (score, breakdown) where score is 0.0-1.0 and breakdown is dict of component scores
    """
    scores = {}
    weights = {}

    # Audio features (librosa) - 35% weight
    if audio_features_a and audio_features_b:
        scores["timbre"] = compare_audio_features(audio_features_a, audio_features_b)
        weights["timbre"] = 0.35

    # BPM similarity - 20% weight
    if audio_features_a and audio_features_b and audio_features_a.bpm > 0 and audio_features_b.bpm > 0:
        bpm_diff = abs(audio_features_a.bpm - audio_features_b.bpm)
        max_bpm = max(audio_features_a.bpm, audio_features_b.bpm)
        scores["tempo"] = 1.0 - min(bpm_diff / max_bpm, 1.0)
        weights["tempo"] = 0.20

    # Energy similarity - 15% weight
    if audio_features_a and audio_features_b:
        energy_diff = abs(audio_features_a.rms_energy - audio_features_b.rms_energy)
        max_energy = max(audio_features_a.rms_energy, audio_features_b.rms_energy, 0.001)
        scores["energy"] = 1.0 - min(energy_diff / max_energy, 1.0)
        weights["energy"] = 0.15

    # Valence similarity - 15% weight
    if acoustic_features_a and acoustic_features_b:
        scores["valence"] = 1.0 - abs(acoustic_features_a.valence - acoustic_features_b.valence)
        weights["valence"] = 0.15

    # Danceability similarity - 10% weight
    if acoustic_features_a and acoustic_features_b:
        scores["dance"] = 1.0 - abs(acoustic_features_a.danceability - acoustic_features_b.danceability)
        weights["dance"] = 0.10

    # Last.fm similarity - 5% weight
    if lastfm_match > 0:
        scores["lastfm"] = lastfm_match
        weights["lastfm"] = 0.05

    # Compute weighted average
    if not scores:
        return 0.0, {}

    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0, {}

    weighted_sum = sum(scores[k] * weights[k] for k in scores)
    final_score = weighted_sum / total_weight

    # Normalize weights for breakdown
    breakdown = {k: scores[k] for k in scores}

    return min(max(final_score, 0.0), 1.0), breakdown


def rank_by_similarity(
    target_audio: Optional[AudioFeatures],
    target_acoustic: Optional[AcousticBrainzFeatures],
    candidates: list[dict],
) -> list[SimilarityResult]:
    """
    Rank candidate tracks by similarity to target.

    candidates: list of dicts with keys:
        - track_id, title, artist, preview_url, album_art, deezer_url
        - audio_features (AudioFeatures or None)
        - acoustic_features (AcousticBrainzFeatures or None)
        - lastfm_match (float, 0-1)

    Returns: list of SimilarityResult sorted by similarity_score descending
    """
    results = []

    for cand in candidates:
        score, breakdown = compute_weighted_similarity(
            target_audio,
            cand.get("audio_features"),
            target_acoustic,
            cand.get("acoustic_features"),
            cand.get("lastfm_match", 0.0),
        )

        results.append(SimilarityResult(
            track_id=cand["track_id"],
            title=cand["title"],
            artist=cand["artist"],
            similarity_score=score,
            preview_url=cand.get("preview_url", ""),
            album_art=cand.get("album_art", ""),
            deezer_url=cand.get("deezer_url", ""),
            timbre_score=breakdown.get("timbre", 0.0),
            tempo_score=breakdown.get("tempo", 0.0),
            energy_score=breakdown.get("energy", 0.0),
            valence_score=breakdown.get("valence", 0.0),
            dance_score=breakdown.get("dance", 0.0),
        ))

    # Sort by similarity score descending
    results.sort(key=lambda x: x.similarity_score, reverse=True)

    return results
